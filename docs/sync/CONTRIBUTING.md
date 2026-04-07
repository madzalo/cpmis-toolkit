# Contributing to CPMIS Sync Rescue

Thank you for your interest in contributing to CPMIS Sync Rescue! This document provides guidelines for contributing to the project.

## 🚀 Getting Started

1. **Fork the repository**
   ```bash
   git clone https://github.com/madzalo/cpmis-sync-rescue.git
   cd cpmis-sync-rescue
   ```

2. **Set up development environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **Run tests**
   ```bash
   just test
   ```

## 📝 How to Contribute

### Reporting Bugs

- Check existing issues first
- Include Python version and OS
- Provide steps to reproduce
- Include error messages and logs

### Suggesting Features

- Open an issue with `[Feature]` prefix
- Describe the use case
- Explain the expected behavior

### Submitting Pull Requests

1. Create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes
   - Follow existing code style
   - Add tests if applicable
   - Update documentation

3. Commit with clear messages
   ```bash
   git commit -m "Add: description of your change"
   ```

4. Push and create PR
   ```bash
   git push origin feature/your-feature-name
   ```

## 📋 Code Style

- Use Python 3.8+ features
- Follow PEP 8 guidelines
- Use type hints where possible
- Keep functions focused and small
- Add docstrings for public functions

## 🏗️ Project Structure

```
src/
├── cli.py              # Command-line interface
├── config.py           # Configuration management
├── extractor.py        # Data extraction from SQLite
├── validator.py        # Dry-run validation
├── importer.py         # DHIS2 data import
├── verifier.py         # Server-side verification
├── batch_processor.py  # Batch processing logic
└── utils.py            # Utilities and helpers
```

## 🔧 Development Commands

```bash
just help           # Show available commands
just test           # Run tests
just clean          # Clean generated files
just process-imports # Run batch import
```

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 💬 Questions?

Open an issue or contact [@madzalo](https://github.com/madzalo).

---

**Thank you for contributing!** 🎉
