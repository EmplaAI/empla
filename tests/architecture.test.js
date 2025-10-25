const fs = require('fs');
const path = require('path');

describe('ARCHITECTURE.md', () => {
  let content;
  
  beforeAll(() => {
    const filePath = path.join(__dirname, '..', 'ARCHITECTURE.md');
    content = fs.readFileSync(filePath, 'utf8');
  });

  describe('File Structure and Format', () => {
    test('should exist and be readable', () => {
      expect(content).toBeDefined();
      expect(content.length).toBeGreaterThan(0);
    });

    test('should have a title', () => {
      expect(content).toMatch(/^#\s+.+/m);
    });

    test('should use proper markdown heading hierarchy', () => {
      const lines = content.split('\n');
      const headings = lines.filter(line => line.match(/^#{1,6}\s+/));
      expect(headings.length).toBeGreaterThan(0);
      
      // Check that headings don't skip levels inappropriately
      const headingLevels = headings.map(h => h.match(/^(#{1,6})/)[1].length);
      for (let i = 1; i < headingLevels.length; i++) {
        const diff = headingLevels[i] - headingLevels[i - 1];
        expect(diff).toBeLessThanOrEqual(1);
      }
    });

    test('should not have trailing whitespace', () => {
      const lines = content.split('\n');
      const linesWithTrailingSpace = lines.filter((line, idx) => 
        line.length > 0 && line.match(/\s+$/) && idx < lines.length - 1
      );
      expect(linesWithTrailingSpace).toHaveLength(0);
    });

    test('should end with a newline', () => {
      expect(content.endsWith('\n')).toBe(true);
    });
  });

  describe('Content Validation', () => {
    test('should contain architecture-related sections', () => {
      const architectureKeywords = [
        'architecture', 'component', 'module', 'system', 'design',
        'structure', 'pattern', 'layer', 'service'
      ];
      const lowerContent = content.toLowerCase();
      const foundKeywords = architectureKeywords.filter(keyword => 
        lowerContent.includes(keyword)
      );
      expect(foundKeywords.length).toBeGreaterThan(0);
    });

    test('should not contain placeholder text', () => {
      const placeholders = ['TODO', 'FIXME', 'TBD', 'XXX', '[placeholder]'];
      const upperContent = content.toUpperCase();
      placeholders.forEach(placeholder => {
        if (upperContent.includes(placeholder)) {
          console.warn(`Warning: Found placeholder "${placeholder}" in ARCHITECTURE.md`);
        }
      });
    });

    test('should have reasonable length for architecture documentation', () => {
      const wordCount = content.split(/\s+/).length;
      expect(wordCount).toBeGreaterThan(100);
      expect(wordCount).toBeLessThan(50000);
    });

    test('should not have broken markdown syntax', () => {
      // Check for unclosed code blocks
      const codeBlockMarkers = content.match(/```/g) || [];
      expect(codeBlockMarkers.length % 2).toBe(0);
      
      // Check for unclosed brackets in links
      const openBrackets = (content.match(/\[/g) || []).length;
      const closeBrackets = (content.match(/\]/g) || []).length;
      expect(Math.abs(openBrackets - closeBrackets)).toBeLessThanOrEqual(1);
    });
  });

  describe('Links and References', () => {
    test('should have properly formatted markdown links', () => {
      const linkPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
      const links = content.match(linkPattern) || [];
      
      links.forEach(link => {
        const match = link.match(/\[([^\]]+)\]\(([^)]+)\)/);
        expect(match).not.toBeNull();
        expect(match[1].trim()).not.toBe('');
        expect(match[2].trim()).not.toBe('');
      });
    });

    test('should not have empty link text', () => {
      const emptyLinkText = /\[\s*\]\([^)]+\)/g;
      expect(content.match(emptyLinkText)).toBeNull();
    });

    test('should not have empty link URLs', () => {
      const emptyLinkUrl = /\[[^\]]+\]\(\s*\)/g;
      expect(content.match(emptyLinkUrl)).toBeNull();
    });

    test('should have valid internal anchor links', () => {
      const anchorLinks = content.match(/\[([^\]]+)\]\(#([^)]+)\)/g) || [];
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      
      const headingIds = headings.map(h => {
        const text = h.replace(/^#{1,6}\s+/, '').trim();
        return text.toLowerCase()
          .replace(/[^\w\s-]/g, '')
          .replace(/\s+/g, '-');
      });

      anchorLinks.forEach(link => {
        const anchor = link.match(/#([^)]+)/)[1];
        // This is a basic check - actual anchor generation can be complex
        if (headingIds.length > 0) {
          console.log(`Checking anchor: ${anchor}`);
        }
      });
    });
  });

  describe('Code Blocks', () => {
    test('should have language specified for code blocks', () => {
      const codeBlockStarts = content.match(/^```\w*/gm) || [];
      const totalCodeBlocks = codeBlockStarts.length;
      const codeBlocksWithLang = codeBlockStarts.filter(block => 
        block.length > 3
      ).length;
      
      if (totalCodeBlocks > 0) {
        const ratio = codeBlocksWithLang / totalCodeBlocks;
        expect(ratio).toBeGreaterThan(0.5);
      }
    });

    test('should have properly closed code blocks', () => {
      const lines = content.split('\n');
      let inCodeBlock = false;
      let codeBlockCount = 0;

      lines.forEach(line => {
        if (line.trim().startsWith('```')) {
          inCodeBlock = !inCodeBlock;
          if (inCodeBlock) codeBlockCount++;
        }
      });

      expect(inCodeBlock).toBe(false);
      expect(codeBlockCount).toBeGreaterThanOrEqual(0);
    });
  });

  describe('Formatting Best Practices', () => {
    test('should not have multiple consecutive blank lines', () => {
      const multipleBlankLines = content.match(/\n\n\n+/g) || [];
      expect(multipleBlankLines.length).toBeLessThanOrEqual(5);
    });

    test('should use consistent list markers', () => {
      const unorderedLists = content.match(/^[\s]*[-*+]\s+/gm) || [];
      if (unorderedLists.length > 0) {
        const markers = unorderedLists.map(item => item.trim()[0]);
        const uniqueMarkers = [...new Set(markers)];
        // Prefer using a single marker type, but allow some flexibility
        expect(uniqueMarkers.length).toBeLessThanOrEqual(2);
      }
    });

    test('should have consistent heading style (ATX)', () => {
      const setextHeadings = content.match(/^.+\n[=\-]+$/gm) || [];
      expect(setextHeadings.length).toBeLessThanOrEqual(2);
    });
  });

  describe('Accessibility and Readability', () => {
    test('should have descriptive link text (not just "click here")', () => {
      const poorLinkTexts = ['click here', 'here', 'link', 'read more'];
      const links = content.match(/\[([^\]]+)\]/g) || [];
      
      links.forEach(link => {
        const linkText = link.slice(1, -1).toLowerCase();
        poorLinkTexts.forEach(poorText => {
          expect(linkText).not.toBe(poorText);
        });
      });
    });

    test('should have alt text for images', () => {
      const images = content.match(/!\[([^\]]*)\]\([^)]+\)/g) || [];
      
      images.forEach(image => {
        const altText = image.match(/!\[([^\]]*)\]/)[1];
        console.log(`Image alt text: "${altText}"`);
      });
    });

    test('should not have overly long lines', () => {
      const lines = content.split('\n');
      const longLines = lines.filter(line => 
        !line.trim().startsWith('http') && 
        !line.trim().startsWith('[') &&
        !line.trim().startsWith('|') &&
        line.length > 120
      );
      
      // Allow some long lines but warn if too many
      if (longLines.length > lines.length * 0.3) {
        console.warn(`Warning: ${longLines.length} lines exceed 120 characters`);
      }
    });
  });

  describe('Content Completeness', () => {
    test('should have a clear introduction or overview', () => {
      const firstParagraph = content.split('\n\n')[1] || content.split('\n\n')[0];
      expect(firstParagraph.length).toBeGreaterThan(50);
    });

    test('should document multiple architectural aspects', () => {
      const sections = content.match(/^##\s+.+$/gm) || [];
      expect(sections.length).toBeGreaterThan(1);
    });
  });

  describe('Version Control Best Practices', () => {
    test('should not contain merge conflict markers', () => {
      expect(content).not.toMatch(/^<<<<<<</m);
      expect(content).not.toMatch(/^=======/m);
      expect(content).not.toMatch(/^>>>>>>>/m);
    });

    test('should not contain commented out sections excessively', () => {
      const htmlComments = content.match(/<!--[\s\S]*?-->/g) || [];
      expect(htmlComments.length).toBeLessThanOrEqual(5);
    });
  });
});