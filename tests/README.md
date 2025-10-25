# Documentation Test Suite

This directory contains comprehensive unit and integration tests for the project's markdown documentation files.

## Test Structure

- `architecture.test.js` - Tests for ARCHITECTURE.md
- `claude.test.js` - Tests for CLAUDE.md
- `readme.test.js` - Tests for README.md
- `integration.test.js` - Cross-document integration tests
- `validate-links.js` - Link validation utility
- `run-all-tests.js` - Comprehensive test runner

## Running Tests

```bash
# Install dependencies
npm install

# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run with coverage
npm run test:coverage

# Validate links only
npm run validate:links

# Lint markdown files
npm run lint:markdown
```

## Test Categories

### File Structure Tests

- Validates Markdown syntax and formatting
- Checks heading hierarchy
- Ensures proper file structure

### Content Validation Tests

- Verifies presence of key sections
- Checks for placeholder text
- Validates content completeness

### Link Tests

- Validates all internal and external links
- Checks anchor links against headings
- Verifies relative file references

### Code Block Tests

- Ensures proper code block formatting
- Validates language specifiers
- Checks for unclosed blocks

### Accessibility Tests

- Validates alt text for images
- Checks for descriptive link text
- Ensures readable content structure

### Integration Tests

- Cross-document consistency
- Terminology consistency
- Inter-document references

## Adding New Tests

When adding new documentation or modifying existing docs:

1. Add tests for new sections in the appropriate test file
2. Update integration tests if adding new documents
3. Run the full test suite before committing
4. Ensure all tests pass and coverage remains high

## Continuous Integration

These tests are designed to run in CI/CD pipelines to ensure documentation quality with every commit.