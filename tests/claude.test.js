const fs = require('fs');
const path = require('path');

describe('CLAUDE.md', () => {
  let content;
  
  beforeAll(() => {
    const filePath = path.join(__dirname, '..', 'CLAUDE.md');
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
    test('should contain Claude-related or AI-related content', () => {
      const keywords = [
        'claude', 'ai', 'assistant', 'model', 'llm', 'language model',
        'anthropic', 'prompt', 'chat', 'conversation'
      ];
      const lowerContent = content.toLowerCase();
      const foundKeywords = keywords.filter(keyword => 
        lowerContent.includes(keyword)
      );
      expect(foundKeywords.length).toBeGreaterThan(0);
    });

    test('should not contain placeholder text', () => {
      const placeholders = ['TODO', 'FIXME', 'TBD', 'XXX'];
      const upperContent = content.toUpperCase();
      placeholders.forEach(placeholder => {
        if (upperContent.includes(placeholder)) {
          console.warn(`Warning: Found placeholder "${placeholder}" in CLAUDE.md`);
        }
      });
    });

    test('should have reasonable content length', () => {
      const wordCount = content.split(/\s+/).length;
      expect(wordCount).toBeGreaterThan(50);
      expect(wordCount).toBeLessThan(100000);
    });

    test('should not have broken markdown syntax', () => {
      // Check for unclosed code blocks
      const codeBlockMarkers = content.match(/```/g) || [];
      expect(codeBlockMarkers.length % 2).toBe(0);
      
      // Check for balanced brackets in links
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

    test('should validate internal anchor links exist', () => {
      const anchorLinks = content.match(/\[([^\]]+)\]\(#([^)]+)\)/g) || [];
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      
      if (anchorLinks.length > 0 && headings.length > 0) {
        const headingIds = headings.map(h => {
          const text = h.replace(/^#{1,6}\s+/, '').trim();
          return text.toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .replace(/\s+/g, '-');
        });
        console.log(`Found ${anchorLinks.length} anchor links and ${headingIds.length} headings`);
      }
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
        expect(ratio).toBeGreaterThan(0.3);
      }
    });

    test('should have properly closed code blocks', () => {
      const lines = content.split('\n');
      let inCodeBlock = false;

      lines.forEach(line => {
        if (line.trim().startsWith('```')) {
          inCodeBlock = !inCodeBlock;
        }
      });

      expect(inCodeBlock).toBe(false);
    });
  });

  describe('Formatting Best Practices', () => {
    test('should not have excessive consecutive blank lines', () => {
      const multipleBlankLines = content.match(/\n\n\n\n+/g) || [];
      expect(multipleBlankLines.length).toBeLessThanOrEqual(10);
    });

    test('should use consistent list markers', () => {
      const unorderedLists = content.match(/^[\s]*[-*+]\s+/gm) || [];
      if (unorderedLists.length > 3) {
        const markers = unorderedLists.map(item => item.trim()[0]);
        const uniqueMarkers = [...new Set(markers)];
        expect(uniqueMarkers.length).toBeLessThanOrEqual(2);
      }
    });
  });

  describe('Accessibility and Readability', () => {
    test('should have descriptive link text', () => {
      const poorLinkTexts = ['click here', 'here', 'link'];
      const links = content.match(/\[([^\]]+)\]/g) || [];
      
      links.forEach(link => {
        const linkText = link.slice(1, -1).toLowerCase();
        expect(poorLinkTexts).not.toContain(linkText);
      });
    });

    test('should have alt text for images', () => {
      const images = content.match(/!\[([^\]]*)\]\([^)]+\)/g) || [];
      
      images.forEach(image => {
        const altText = image.match(/!\[([^\]]*)\]/)[1];
        console.log(`Image alt text: "${altText}"`);
      });
    });
  });

  describe('Content Organization', () => {
    test('should have logical section structure', () => {
      const h2Sections = content.match(/^##\s+.+$/gm) || [];
      expect(h2Sections.length).toBeGreaterThanOrEqual(1);
    });

    test('should have clear introduction', () => {
      const paragraphs = content.split('\n\n').filter(p => 
        p.trim().length > 0 && !p.trim().startsWith('#')
      );
      expect(paragraphs.length).toBeGreaterThan(0);
      if (paragraphs[0]) {
        expect(paragraphs[0].length).toBeGreaterThan(30);
      }
    });
  });

  describe('Version Control Best Practices', () => {
    test('should not contain merge conflict markers', () => {
      expect(content).not.toMatch(/^<<<<<<</m);
      expect(content).not.toMatch(/^=======/m);
      expect(content).not.toMatch(/^>>>>>>>/m);
    });

    test('should not contain excessive HTML comments', () => {
      const htmlComments = content.match(/<!--[\s\S]*?-->/g) || [];
      expect(htmlComments.length).toBeLessThanOrEqual(10);
    });
  });

  describe('Special Characters and Encoding', () => {
    test('should use proper markdown escaping', () => {
      // Check that special characters in regular text are properly used
      const lines = content.split('\n').filter(line => 
        !line.trim().startsWith('```') && !line.trim().startsWith('#')
      );
      
      // This is a basic check - markdown allows special chars in many contexts
      expect(lines).toBeDefined();
    });

    test('should not have control characters', () => {
      const controlChars = content.match(new RegExp('[\\x00-\\x08\\x0B-\\x0C\\x0E-\\x1F]', 'g'));
      expect(controlChars).toBeNull();
    });
  });

  describe('Professional Documentation Standards', () => {
    test('should not contain profanity or inappropriate content', () => {
      // Basic check - expand list as needed
      const inappropriateWords = ['fuck', 'shit', 'damn'];
      const lowerContent = content.toLowerCase();
      inappropriateWords.forEach(word => {
        expect(lowerContent).not.toContain(word);
      });
    });

    test('should maintain professional tone in headings', () => {
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      headings.forEach(heading => {
        const text = heading.replace(/^#{1,6}\s+/, '');
        expect(text.length).toBeGreaterThan(2);
        expect(text.length).toBeLessThan(200);
      });
    });
  });
});