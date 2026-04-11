# Architecture Overview

## How It Works

Each module follows the same pattern:
1. Accept input (file, dict, or natural language string)
2. Build a structured prompt for Claude
3. Parse the structured JSON response
4. Return a typed Python dataclass with the results

## Claude Integration

All modules use the Anthropic Python SDK. The default model is `claude-opus-4-6` for maximum reasoning quality. You can override this to `claude-sonnet-4-6` for faster/cheaper analysis on large inventories.

```python
# Use Sonnet for bulk analysis
analyzer = CloudIQAnalyzer(model="claude-sonnet-4-6")

# Use Opus for complex assessments
checker = PolicyChecker(model="claude-opus-4-6")
```

## Extending

Each module is independently usable. You can:
- Chain them: `cloudiq → migration_scout → executive_report`
- Use individually: just `policy_guard` for compliance audits
- Build custom prompts by subclassing any module

## Cost

Typical costs per analysis (Claude Opus):
- CloudIQ single config: ~$0.05
- MigrationScout 20 workloads: ~$0.15
- PolicyGuard single file: ~$0.04
- ExecutiveReport generation: ~$0.06

Full pipeline demo: ~$0.30 total

## Production Use

For production use at enterprise scale:
- Cache repeated analyses using the `raw_analysis` field
- Use Sonnet for initial screening, Opus for critical assessments
- Add rate limiting for bulk operations
- Store results in a database for trend analysis
