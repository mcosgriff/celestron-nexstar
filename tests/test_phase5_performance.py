"""
Phase 5 Performance and Edge Case Tests

Tests for command tracker performance and edge cases.
"""

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from celestron_nexstar.api.telescope.command_tracker import CommandTracker


def test_command_tracker_high_volume():
    """Test command tracker with high volume of commands."""
    print("Test 1: High Volume Command Tracking (1000 commands)")
    print("-" * 60)

    tracker = CommandTracker(max_history=1000)
    start_time = time.time()

    # Record 1000 commands
    for i in range(1000):
        command = f"CMD{i % 10}"  # Rotate through 10 different commands
        tracker.start_command(command)
        tracker.record_command(
            command=command,
            response=f"RESP{i}",
            success=True,
            decoded=f"Position update {i}",
        )

    elapsed = time.time() - start_time
    print(f"  Time to record 1000 commands: {elapsed:.4f}s")
    print(f"  Average per command: {(elapsed / 1000) * 1000:.4f}ms")

    # Verify circular buffer
    history = tracker.get_history()
    print(f"  History size: {len(history)}")
    print(f"  Expected: 1000 (circular buffer)")

    # Verify statistics
    stats = tracker.get_statistics()
    print(f"  Total commands: {stats['total_commands']}")
    print(f"  Success rate: {stats['success_rate']:.1f}%")
    print(f"  Average duration: {stats['average_duration_ms']:.4f}ms")

    assert len(history) == 1000, "Should store 1000 commands"
    assert stats["total_commands"] == 1000
    assert stats["success_rate"] == 100.0

    print("  ✓ PASS")
    print()


def test_command_tracker_circular_buffer_overflow():
    """Test circular buffer overflow behavior."""
    print("Test 2: Circular Buffer Overflow (max=100, add 200)")
    print("-" * 60)

    tracker = CommandTracker(max_history=100)

    # Add 200 commands
    for i in range(200):
        tracker.record_command(
            command=f"CMD{i}", response=f"RESP{i}", success=True, decoded=None
        )

    history = tracker.get_history()
    print(f"  Added 200 commands to buffer with max=100")
    print(f"  History size: {len(history)}")
    print(f"  First command in history: {history[0].command}")
    print(f"  Last command in history: {history[-1].command}")

    # Should only have last 100 commands
    # Note: deque returns items in reverse order (most recent first)
    assert len(history) == 100, "Should maintain max size"
    assert history[0].command == "CMD199", "Most recent should be first"
    assert history[-1].command == "CMD100", "Oldest kept should be last"

    print("  ✓ PASS")
    print()


def test_command_tracker_empty_history():
    """Test operations on empty command tracker."""
    print("Test 3: Empty History Edge Cases")
    print("-" * 60)

    tracker = CommandTracker(max_history=100)

    # Get history from empty tracker
    history = tracker.get_history()
    print(f"  Empty history length: {len(history)}")
    assert len(history) == 0

    # Get statistics from empty tracker
    stats = tracker.get_statistics()
    print(f"  Empty stats: {stats}")
    assert stats["total_commands"] == 0
    assert stats["successful_commands"] == 0
    assert stats["failed_commands"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["average_duration_ms"] == 0.0

    # Export empty history
    with TemporaryDirectory() as tmpdir:
        export_path = Path(tmpdir) / "empty.json"
        tracker.export_to_json(export_path)
        print(f"  Exported empty history to: {export_path.name}")
        assert export_path.exists()

    print("  ✓ PASS")
    print()


def test_command_tracker_failures():
    """Test command tracker with failures."""
    print("Test 4: Command Failures")
    print("-" * 60)

    tracker = CommandTracker(max_history=100)

    # Mix of success and failures
    for i in range(50):
        tracker.record_command(
            command=f"CMD{i}",
            response=f"RESP{i}" if i % 3 != 0 else None,
            success=i % 3 != 0,
            error="Timeout" if i % 3 == 0 else None,
            decoded=None,
        )

    stats = tracker.get_statistics()
    failed_count = stats["failed_commands"]
    success_rate = stats["success_rate"]

    print(f"  Total commands: {stats['total_commands']}")
    print(f"  Successful: {stats['successful_commands']}")
    print(f"  Failed: {failed_count}")
    print(f"  Success rate: {success_rate:.1f}%")

    # Filter for failed commands only
    failed_history = tracker.get_history(filter_type="failed")
    print(f"  Failed commands in history: {len(failed_history)}")

    assert stats["total_commands"] == 50
    assert failed_count > 0, "Should have failures"
    assert success_rate < 100.0, "Success rate should be less than 100%"
    assert len(failed_history) == failed_count

    print("  ✓ PASS")
    print()


def test_command_tracker_filtering():
    """Test filtering of command history."""
    print("Test 5: History Filtering")
    print("-" * 60)

    tracker = CommandTracker(max_history=100)

    # Add mix of commands
    for i in range(30):
        tracker.record_command(
            command=f"CMD{i}",
            response=f"RESP{i}",
            success=True,
            decoded=None,
        )
    for i in range(10):
        tracker.record_command(
            command=f"FAIL{i}",
            response=None,
            success=False,
            error="Test error",
            decoded=None,
        )

    all_history = tracker.get_history()
    success_history = tracker.get_history(filter_type="success")
    failed_history = tracker.get_history(filter_type="failed")

    print(f"  All commands: {len(all_history)}")
    print(f"  Successful only: {len(success_history)}")
    print(f"  Failed only: {len(failed_history)}")

    assert len(all_history) == 40
    assert len(success_history) == 30
    assert len(failed_history) == 10

    # Verify all successful commands are actually successful
    assert all(cmd.success for cmd in success_history)
    # Verify all failed commands actually failed
    assert all(not cmd.success for cmd in failed_history)

    print("  ✓ PASS")
    print()


def test_command_tracker_export_import():
    """Test JSON export and import."""
    print("Test 6: JSON Export/Import")
    print("-" * 60)

    tracker = CommandTracker(max_history=100)

    # Add some commands
    for i in range(20):
        tracker.record_command(
            command=f"CMD{i}",
            response=f"RESP{i}",
            success=i % 5 != 0,
            error="Error" if i % 5 == 0 else None,
            decoded=f"Decoded{i}",
        )

    with TemporaryDirectory() as tmpdir:
        export_path = Path(tmpdir) / "commands.json"

        # Export
        tracker.export_to_json(export_path)
        print(f"  Exported to: {export_path.name}")
        assert export_path.exists()

        # Check file size
        file_size = export_path.stat().st_size
        print(f"  File size: {file_size} bytes")
        assert file_size > 0

        # Verify JSON structure by reading it back
        import json

        with open(export_path) as f:
            data = json.load(f)

        print(f"  Commands in export: {len(data.get('commands', []))}")
        print(f"  Statistics in export: {list(data.get('statistics', {}).keys())}")

        assert "commands" in data
        assert "statistics" in data
        assert len(data["commands"]) == 20

    print("  ✓ PASS")
    print()


def test_command_tracker_rapid_commands():
    """Test rapid command execution (100 commands/sec simulation)."""
    print("Test 7: Rapid Commands (100 commands in quick succession)")
    print("-" * 60)

    tracker = CommandTracker(max_history=200)
    start_time = time.time()

    # Simulate 100 rapid commands
    for i in range(100):
        tracker.start_command(f"CMD{i}")
        # Minimal delay to simulate rapid execution
        time.sleep(0.001)  # 1ms
        tracker.record_command(
            command=f"CMD{i}",
            response=f"RESP{i}",
            success=True,
            decoded=None,
        )

    elapsed = time.time() - start_time
    rate = 100 / elapsed

    print(f"  Time for 100 commands: {elapsed:.4f}s")
    print(f"  Rate: {rate:.1f} commands/sec")

    history = tracker.get_history()
    print(f"  Commands recorded: {len(history)}")

    assert len(history) == 100
    assert rate > 50, "Should handle at least 50 commands/sec"

    print("  ✓ PASS")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 5: Performance and Edge Case Tests")
    print("=" * 60)
    print()

    try:
        test_command_tracker_high_volume()
        test_command_tracker_circular_buffer_overflow()
        test_command_tracker_empty_history()
        test_command_tracker_failures()
        test_command_tracker_filtering()
        test_command_tracker_export_import()
        test_command_tracker_rapid_commands()

        print("=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        raise
