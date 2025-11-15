"""
Astronomy RSS Feed Integration

Fetches and stores astronomy news and night sky events from multiple RSS feed sources.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp
import feedparser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from celestron_nexstar.api.database.models import RSSFeedModel


logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_RSS_FEEDS",
    "RSSFeedSource",
    "SkyAtAGlanceArticle",
    "fetch_all_rss_feeds",
    "fetch_and_store_rss_feed",
    "get_article_by_title",
    "get_articles_this_month",
    "get_articles_this_week",
]


@dataclass
class RSSFeedSource:
    """Represents an RSS feed source for astronomy news."""

    name: str
    url: str
    description: str


# Registry of available RSS feed sources
DEFAULT_RSS_FEEDS: dict[str, RSSFeedSource] = {
    "sky-telescope": RSSFeedSource(
        name="Sky & Telescope",
        url="https://skyandtelescope.org/observing/sky-at-a-glance/feed/",
        description="Weekly 'Sky at a Glance' articles with observing highlights",
    ),
    "astronomy": RSSFeedSource(
        name="Astronomy Magazine",
        url="https://www.astronomy.com/feed/",
        description="Astronomy news, articles, and event highlights",
    ),
    "earthsky": RSSFeedSource(
        name="EarthSky",
        url="https://earthsky.org/feed/",
        description="Daily astronomy news and event updates",
    ),
    "space-com": RSSFeedSource(
        name="Space.com",
        url="https://www.space.com/feeds/all",
        description="Space news and astronomy events",
    ),
    "nasa": RSSFeedSource(
        name="NASA News",
        url="https://www.nasa.gov/rss/dyn/breaking_news.rss",
        description="NASA mission updates and space events",
    ),
    "in-the-sky": RSSFeedSource(
        name="In-The-Sky.org",
        url="https://in-the-sky.org/rss.php",
        description="Daily astronomy events and object visibility",
    ),
}


@dataclass
class SkyAtAGlanceArticle:
    """Represents a Sky at a Glance article."""

    title: str
    link: str
    guid: str | None
    description: str
    content: str | None
    published_date: datetime
    author: str | None
    categories: list[str] | None
    source: str = "Sky & Telescope"
    feed_url: str = "https://skyandtelescope.org/observing/sky-at-a-glance/feed/"

    def __post_init__(self) -> None:
        """Ensure published_date is timezone-aware."""
        if self.published_date.tzinfo is None:
            self.published_date = self.published_date.replace(tzinfo=UTC)


async def fetch_and_store_rss_feed(
    feed_url: str,
    source_name: str = "Unknown Source",
    db_session: AsyncSession | None = None,
) -> int:
    """
    Fetch RSS feed and store articles in database.

    Args:
        feed_url: URL of the RSS feed
        source_name: Name of the feed source (e.g., "Sky & Telescope")
        db_session: Database session (if None, will create a new one)

    Returns:
        Number of new articles added to the database
    """
    if db_session is None:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as session:
            return await fetch_and_store_rss_feed(feed_url, source_name, session)

    try:
        logger.info(f"Fetching RSS feed from {feed_url}")

        # Fetch RSS feed with proper headers to avoid 403 errors
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with (
            aiohttp.ClientSession() as http_session,
            http_session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                raise RuntimeError(f"Failed to fetch RSS feed: HTTP {response.status}")

            content = await response.text()

        # Parse RSS feed
        feed = feedparser.parse(content)

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"RSS feed parsing warning: {feed.bozo_exception}")

        fetched_at = datetime.now(UTC)
        new_count = 0

        # Process each entry
        for entry in feed.entries:
            try:
                # Extract data from entry
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                guid = entry.get("id") or entry.get("guid", "").strip() or None

                # Get description (may be HTML)
                description = ""
                if "description" in entry:
                    description = entry.description
                elif "summary" in entry:
                    description = entry.summary

                # Get content if available
                article_content: str | None = None
                if "content" in entry and entry.content:
                    # content is a list of dicts with 'value' keys
                    content_parts = [c.get("value", "") for c in entry.content if isinstance(c, dict)]
                    if content_parts:
                        article_content = "\n\n".join(content_parts)

                # Parse published date
                published_date = datetime.now(UTC)
                if "published_parsed" in entry and entry.published_parsed:
                    try:
                        # published_parsed is a 9-tuple: (year, month, day, hour, minute, second, weekday, julian_day, dst_flag)
                        # We only need the first 6 elements for datetime
                        parsed_tuple = entry.published_parsed[:6]
                        published_date = datetime(
                            parsed_tuple[0],  # year
                            parsed_tuple[1],  # month
                            parsed_tuple[2],  # day
                            parsed_tuple[3],  # hour
                            parsed_tuple[4],  # minute
                            parsed_tuple[5],  # second
                            tzinfo=UTC,
                        )
                    except (ValueError, TypeError, IndexError):
                        logger.warning(f"Could not parse published date for {title}, using current time")
                elif "published" in entry:
                    # Try to parse the published string
                    try:
                        from email.utils import parsedate_to_datetime

                        published_date = parsedate_to_datetime(entry.published)
                        if published_date.tzinfo is None:
                            published_date = published_date.replace(tzinfo=UTC)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse published date string for {title}, using current time")

                # Get author
                author = None
                if "author" in entry:
                    author = entry.author
                elif "author_detail" in entry and "name" in entry.author_detail:
                    author = entry.author_detail.name

                # Get categories/tags
                categories = None
                if "tags" in entry and entry.tags:
                    categories = [tag.get("term", "") for tag in entry.tags if tag.get("term")]
                elif "category" in entry:
                    if isinstance(entry.category, list):
                        categories = [str(c) for c in entry.category]
                    else:
                        categories = [str(entry.category)]

                # Check if article already exists (by link or guid)
                from sqlalchemy import or_

                conditions = [RSSFeedModel.link == link]
                if guid:
                    conditions.append(RSSFeedModel.guid == guid)
                stmt = select(RSSFeedModel).where(or_(*conditions))

                result = await db_session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    # Update existing article
                    existing.title = title
                    existing.description = description
                    existing.content = article_content
                    existing.published_date = published_date
                    existing.author = author
                    existing.categories = json.dumps(categories) if categories else None
                    existing.updated_at = datetime.now(UTC)
                    existing.fetched_at = fetched_at
                    logger.debug(f"Updated existing article: {title}")
                else:
                    # Create new article
                    article = RSSFeedModel(
                        title=title,
                        link=link,
                        guid=guid,
                        description=description,
                        content=article_content,
                        published_date=published_date,
                        author=author,
                        categories=json.dumps(categories) if categories else None,
                        source=source_name,
                        feed_url=feed_url,
                        fetched_at=fetched_at,
                    )
                    db_session.add(article)
                    new_count += 1
                    logger.debug(f"Added new article: {title}")

            except Exception as e:
                logger.warning(f"Error processing RSS entry: {e}", exc_info=True)
                continue

        await db_session.commit()
        logger.info(f"RSS feed processed: {new_count} new articles added from {source_name}")
        return new_count

    except Exception as e:
        logger.error(f"Error fetching RSS feed from {source_name} ({feed_url}): {e}", exc_info=True)
        await db_session.rollback()
        raise


async def fetch_all_rss_feeds(
    feed_sources: dict[str, RSSFeedSource] | None = None,
    db_session: AsyncSession | None = None,
) -> dict[str, int]:
    """
    Fetch all RSS feeds from the registry and store articles in database.

    Args:
        feed_sources: Dictionary of feed sources to fetch (defaults to DEFAULT_RSS_FEEDS)
        db_session: Database session (if None, will create a new one)

    Returns:
        Dictionary mapping source names to number of new articles added
    """
    if feed_sources is None:
        feed_sources = DEFAULT_RSS_FEEDS

    if db_session is None:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as session:
            return await fetch_all_rss_feeds(feed_sources, session)

    results: dict[str, int] = {}

    for source in feed_sources.values():
        try:
            new_count = await fetch_and_store_rss_feed(source.url, source.name, db_session)
            results[source.name] = new_count
        except Exception as e:
            logger.error(f"Failed to fetch feed from {source.name}: {e}")
            results[source.name] = -1  # Use -1 to indicate error

    return results


async def get_articles_this_week(db_session: AsyncSession | None = None) -> list[SkyAtAGlanceArticle]:
    """
    Get articles published in the last 7 days.

    Args:
        db_session: Database session (if None, will create a new one)

    Returns:
        List of articles from the last week
    """
    if db_session is None:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as session:
            return await get_articles_this_week(session)

    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)

    stmt = (
        select(RSSFeedModel).where(RSSFeedModel.published_date >= week_ago).order_by(RSSFeedModel.published_date.desc())
    )

    result = await db_session.execute(stmt)
    models = result.scalars().all()

    articles = []
    for model in models:
        categories = json.loads(model.categories) if model.categories else None
        article = SkyAtAGlanceArticle(
            title=model.title,
            link=model.link,
            guid=model.guid,
            description=model.description,
            content=model.content,
            published_date=model.published_date,
            author=model.author,
            categories=categories,
            source=model.source,
            feed_url=model.feed_url,
        )
        articles.append(article)

    return articles


async def get_articles_this_month(db_session: AsyncSession | None = None) -> list[SkyAtAGlanceArticle]:
    """
    Get articles published in the last 30 days.

    Args:
        db_session: Database session (if None, will create a new one)

    Returns:
        List of articles from the last month
    """
    if db_session is None:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as session:
            return await get_articles_this_month(session)

    now = datetime.now(UTC)
    month_ago = now - timedelta(days=30)

    stmt = (
        select(RSSFeedModel)
        .where(RSSFeedModel.published_date >= month_ago)
        .order_by(RSSFeedModel.published_date.desc())
    )

    result = await db_session.execute(stmt)
    models = result.scalars().all()

    articles = []
    for model in models:
        categories = json.loads(model.categories) if model.categories else None
        article = SkyAtAGlanceArticle(
            title=model.title,
            link=model.link,
            guid=model.guid,
            description=model.description,
            content=model.content,
            published_date=model.published_date,
            author=model.author,
            categories=categories,
            source=model.source,
            feed_url=model.feed_url,
        )
        articles.append(article)

    return articles


async def get_article_by_title(title_query: str, db_session: AsyncSession | None = None) -> SkyAtAGlanceArticle | None:
    """
    Get an article by title (partial match, case-insensitive).

    Args:
        title_query: Title or partial title to search for
        db_session: Database session (if None, will create a new one)

    Returns:
        First matching article, or None if not found
    """
    if db_session is None:
        from celestron_nexstar.api.database.models import get_db_session

        async with get_db_session() as session:
            return await get_article_by_title(title_query, session)

    title_lower = title_query.lower()

    stmt = select(RSSFeedModel).where(RSSFeedModel.title.ilike(f"%{title_lower}%")).limit(1)

    result = await db_session.execute(stmt)
    model = result.scalar_one_or_none()

    if model is None:
        return None

    categories = json.loads(model.categories) if model.categories else None
    return SkyAtAGlanceArticle(
        title=model.title,
        link=model.link,
        guid=model.guid,
        description=model.description,
        content=model.content,
        published_date=model.published_date,
        author=model.author,
        categories=categories,
        source=model.source,
        feed_url=model.feed_url,
    )
