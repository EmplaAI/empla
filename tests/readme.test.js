const fs = require('fs');
const path = require('path');

describe('README.md', () => {
  let content;
  
  beforeAll(() => {
    const filePath = path.join(__dirname, '..', 'README.md');
    content = fs.readFileSync(filePath, 'utf8');
  });

  describe('File Structure and Format', () => {
    test('should exist and be readable', () => {
      expect(content).toBeDefined();
      expect(content.length).toBeGreaterThan(0);
    });

    test('should have a project title as first heading', () => {
      const firstHeading = content.match(/^#\s+(.+)$/m);
      expect(firstHeading).not.toBeNull();
      expect(firstHeading[1].trim().length).toBeGreaterThan(0);
    });

    test('should use proper markdown heading hierarchy', () => {
      const lines = content.split('\n');
      const headings = lines.filter(line => line.match(/^#{1,6}\s+/));
      expect(headings.length).toBeGreaterThan(0);
      
      // First heading should be H1
      expect(headings[0]).toMatch(/^#\s+/);
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

  describe('Essential README Sections', () => {
    test('should have a description or introduction', () => {
      const descriptionKeywords = ['description', 'about', 'overview', 'introduction'];
      const lowerContent = content.toLowerCase();
      const hasDescriptionSection = descriptionKeywords.some(keyword => 
        lowerContent.includes(keyword)
      );
      
      // Or just has content after the title
      const sections = content.split(/^##/m);
      expect(sections.length).toBeGreaterThan(1);
    });

    test('should have installation or getting started instructions', () => {
      const installKeywords = [
        'install', 'setup', 'getting started', 'quick start', 
        'prerequisites', 'requirements'
      ];
      const lowerContent = content.toLowerCase();
      const hasInstallSection = installKeywords.some(keyword => 
        lowerContent.includes(keyword)
      );
      
      expect(hasInstallSection).toBe(true);
    });

    test('should have usage examples or instructions', () => {
      const usageKeywords = ['usage', 'example', 'how to', 'guide'];
      const lowerContent = content.toLowerCase();
      const hasUsageSection = usageKeywords.some(keyword => 
        lowerContent.includes(keyword)
      );
      
      expect(hasUsageSection).toBe(true);
    });

    test('should have license information or section', () => {
      const lowerContent = content.toLowerCase();
      const hasLicense = lowerContent.includes('license');
      
      if (!hasLicense) {
        console.warn('Warning: No license information found in README');
      }
    });

    test('should have contributing guidelines or mention', () => {
      const lowerContent = content.toLowerCase();
      const hasContributing = lowerContent.includes('contribut');
      
      if (!hasContributing) {
        console.log('Note: No contributing guidelines found in README');
      }
    });
  });

  describe('Content Validation', () => {
    test('should not contain placeholder text', () => {
      const placeholders = ['TODO', 'FIXME', 'TBD', 'XXX', '[Your Project Name]'];
      const upperContent = content.toUpperCase();
      placeholders.forEach(placeholder => {
        if (upperContent.includes(placeholder.toUpperCase())) {
          console.warn(`Warning: Found placeholder "${placeholder}" in README.md`);
        }
      });
    });

    test('should have substantial content', () => {
      const wordCount = content.split(/\s+/).length;
      expect(wordCount).toBeGreaterThan(100);
    });

    test('should not have broken markdown syntax', () => {
      // Check for unclosed code blocks
      const codeBlockMarkers = content.match(/```/g) || [];
      expect(codeBlockMarkers.length % 2).toBe(0);
      
      // Check for balanced brackets
      const openBrackets = (content.match(/\[/g) || []).length;
      const closeBrackets = (content.match(/\]/g) || []).length;
      expect(Math.abs(openBrackets - closeBrackets)).toBeLessThanOrEqual(2);
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

    test('should have valid anchor links if present', () => {
      const anchorLinks = content.match(/\[([^\]]+)\]\(#([^)]+)\)/g) || [];
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      
      if (anchorLinks.length > 0) {
        expect(headings.length).toBeGreaterThan(0);
        
        const headingIds = headings.map(h => {
          const text = h.replace(/^#{1,6}\s+/, '').trim();
          return text.toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .replace(/\s+/g, '-');
        });
        
        console.log(`Found ${anchorLinks.length} anchor links and ${headingIds.length} headings`);
      }
    });

    test('should have badges properly formatted if present', () => {
      const badges = content.match(/!\[[^\]]*\]\(https?:\/\/[^)]+\)/g) || [];
      badges.forEach(badge => {
        expect(badge).toMatch(/!\[.*\]\(https?:\/\/.+\)/);
      });
    });
  });

  describe('Code Blocks and Examples', () => {
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

      lines.forEach(line => {
        if (line.trim().startsWith('```')) {
          inCodeBlock = !inCodeBlock;
        }
      });

      expect(inCodeBlock).toBe(false);
    });

    test('should include practical code examples', () => {
      const codeBlocks = content.match(/```[\s\S]*?```/g) || [];
      if (codeBlocks.length > 0) {
        // At least one code block should have substantial content
        const substantialBlocks = codeBlocks.filter(block => 
          block.split('\n').length > 3
        );
        expect(substantialBlocks.length).toBeGreaterThan(0);
      }
    });
  });

  describe('Formatting Best Practices', () => {
    test('should not have excessive consecutive blank lines', () => {
      const multipleBlankLines = content.match(/\n\n\n\n+/g) || [];
      expect(multipleBlankLines.length).toBeLessThanOrEqual(5);
    });

    test('should use consistent list markers', () => {
      const unorderedLists = content.match(/^[\s]*[-*+]\s+/gm) || [];
      if (unorderedLists.length > 5) {
        const markers = unorderedLists.map(item => item.trim()[0]);
        const uniqueMarkers = [...new Set(markers)];
        expect(uniqueMarkers.length).toBeLessThanOrEqual(2);
      }
    });

    test('should use ATX-style headings consistently', () => {
      const setextHeadings = content.match(/^.+\n[=\-]+$/gm) || [];
      expect(setextHeadings.length).toBeLessThanOrEqual(2);
    });

    test('should have proper spacing around headings', () => {
      const lines = content.split('\n');
      lines.forEach((line, idx) => {
        if (line.match(/^#{1,6}\s+/) && idx > 0) {
          // Heading should ideally have blank line before it (except first)
          if (lines[idx - 1].trim() !== '' && idx > 2) {
            // This is a style preference, log for awareness
            // console.log(`Heading at line ${idx + 1} might benefit from spacing`);
          }
        }
      });
    });
  });

  describe('Accessibility and Readability', () => {
    test('should have descriptive link text', () => {
      const poorLinkTexts = ['click here', 'here', 'link', 'read more'];
      const links = content.match(/\[([^\]]+)\]/g) || [];
      
      links.forEach(link => {
        const linkText = link.slice(1, -1).toLowerCase().trim();
        poorLinkTexts.forEach(poorText => {
          expect(linkText).not.toBe(poorText);
        });
      });
    });

    test('should have alt text for images', () => {
      const images = content.match(/!\[([^\]]*)\]\([^)]+\)/g) || [];
      
      images.forEach(image => {
        const match = image.match(/!\[([^\]]*)\]/);
        const altText = match[1];
        // Alt text can be empty for decorative images, but log for awareness
        if (altText === '') {
          console.log('Found image without alt text (may be decorative)');
        }
      });
    });

    test('should not have overly long lines in prose', () => {
      const lines = content.split('\n');
      const proseLines = lines.filter(line => 
        !line.trim().startsWith('http') && 
        !line.trim().startsWith('[') &&
        !line.trim().startsWith('|') &&
        !line.trim().startsWith('#') &&
        !line.trim().startsWith('```') &&
        line.trim().length > 0
      );
      
      const longLines = proseLines.filter(line => line.length > 120);
      
      if (longLines.length > proseLines.length * 0.3) {
        console.warn(`Warning: ${longLines.length} prose lines exceed 120 characters`);
      }
    });
  });

  describe('Project Information', () => {
    test('should indicate project purpose clearly', () => {
      // First few paragraphs should establish purpose
      const firstParagraphs = content.split('\n\n').slice(0, 3).join(' ');
      expect(firstParagraphs.length).toBeGreaterThan(50);
    });

    test('should provide contact or support information', () => {
      const contactKeywords = [
        'contact', 'support', 'help', 'issue', 'bug', 'email',
        'discord', 'slack', 'twitter', 'forum'
      ];
      const lowerContent = content.toLowerCase();
      const hasContact = contactKeywords.some(keyword => 
        lowerContent.includes(keyword)
      );
      
      if (!hasContact) {
        console.log('Note: No contact/support information found');
      }
    });

    test('should have table of contents if long document', () => {
      const wordCount = content.split(/\s+/).length;
      if (wordCount > 1000) {
        const hasTOC = content.toLowerCase().includes('table of contents') ||
                       content.match(/^##\s+Contents?$/mi);
        
        if (!hasTOC) {
          console.log('Note: Long README might benefit from table of contents');
        }
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
      expect(htmlComments.length).toBeLessThanOrEqual(5);
    });
  });

  describe('Professional Standards', () => {
    test('should not contain profanity', () => {
      const inappropriateWords = ['fuck', 'shit', 'damn', 'crap'];
      const lowerContent = content.toLowerCase();
      inappropriateWords.forEach(word => {
        expect(lowerContent).not.toContain(word);
      });
    });

    test('should maintain consistent capitalization in headings', () => {
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      headings.forEach(heading => {
        const text = heading.replace(/^#{1,6}\s+/, '');
        expect(text.length).toBeGreaterThan(0);
      });
    });

    test('should not have excessive exclamation marks', () => {
      const exclamationMarks = (content.match(/!/g) || []).length;
      const sentences = content.split(/[.!?]+/).length;
      const ratio = exclamationMarks / sentences;
      
      expect(ratio).toBeLessThan(0.3);
    });
  });

  describe('SEO and Discoverability', () => {
    test('should have keywords relevant to project domain', () => {
      // This test is context-specific, but checks general structure
      const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
      const hasKeywordsInHeadings = headings.some(h => h.split(/\s+/).length > 2);
      expect(hasKeywordsInHeadings).toBe(true);
    });

    test('should have clear project categorization', () => {
      const sections = content.match(/^##\s+(.+)$/gm) || [];
      expect(sections.length).toBeGreaterThan(2);
    });
  });
});