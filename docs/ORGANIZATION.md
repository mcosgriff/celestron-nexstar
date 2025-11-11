# Documentation Organization

This document describes the organization of documentation files in this project.

## Directory Structure

```
docs/
├── INDEX.md                    # Main documentation index
├── INSTALL.md                  # Installation guide
├── CLI.md                      # CLI command reference
├── DATA_IMPORT.md              # Data import user guide
├── CUSTOM_CATALOG.md           # Custom catalog creation guide
├── CUSTOM_YAML_FEATURE.md      # YAML catalog feature guide
├── CATALOG_DATA_SOURCES.md     # Available catalog sources
├── COSMOS_INTEGRATION.md       # COSMOS/OpenC3 integration
├── TUI_FRAMEWORK_OPTIONS.md    # TUI framework comparison
│
├── history/                     # Completed migrations and phases
│   ├── README.md
│   ├── PHASE_1_COMPLETE.md
│   ├── PHASE_2_COMPLETE.md
│   ├── FRESH_MIGRATION_COMPLETE.md
│   ├── SQLALCHEMY_COMPLETE.md
│   ├── SQLALCHEMY_MIGRATION_PLAN.md
│   ├── DATABASE_GIT_SETUP.md
│   └── CLI_DATA_IMPORT_FEATURE.md
│
├── plans/                       # Future feature plans
│   ├── README.md
│   ├── CATALOG_EXPANSION_PLAN.md
│   ├── WHATS_VISIBLE_TONIGHT_PLAN.md
│   └── FULL_SCREEN_TUI_PLAN.md
│
└── api/                         # API documentation (auto-generated)
    ├── telescope_docs.md
    ├── protocol_docs.md
    ├── types_docs.md
    ├── exceptions_docs.md
    ├── converters_docs.md
    ├── utils_docs.md
    ├── init_docs.md
    ├── examples_docs.md
    └── nexstar_commands.md
```

## File Categories

### User Documentation (docs/)
- **Getting Started**: INSTALL.md, CLI.md
- **User Guides**: DATA_IMPORT.md, CUSTOM_CATALOG.md, CUSTOM_YAML_FEATURE.md
- **Reference**: CATALOG_DATA_SOURCES.md
- **Integration**: COSMOS_INTEGRATION.md, TUI_FRAMEWORK_OPTIONS.md

### Historical Documentation (docs/history/)
Completed migrations, phases, and major changes preserved for reference:
- Database migrations (Phase 1, Phase 2, Fresh Migration, SQLAlchemy)
- Feature completion documents
- Setup instructions that may still be useful

### Future Plans (docs/plans/)
Planning documents for future features:
- Catalog expansion roadmap (partially complete)
- Feature implementation plans
- Architecture proposals

### API Documentation (docs/api/)
Auto-generated API reference documentation for developers.

## Maintenance

- **Historical docs**: Keep for reference, update only if critical information changes
- **Plan docs**: Update status as features are implemented
- **User docs**: Keep current with code changes
- **API docs**: Regenerate when API changes

