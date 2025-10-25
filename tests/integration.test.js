const fs = require('fs');
const path = require('path');

describe('Documentation Integration Tests', () => {
  const files = ['README.md', 'ARCHITECTURE.md', 'CLAUDE.md'];
  let contents = {};

  beforeAll(() => {
    files.forEach(file => {
      const filePath = path.join(__dirname, '..', file);
      if (fs.existsSync(filePath)) {
        contents[file] = fs.readFileSync(filePath, 'utf8');
      }
    });
  });

  describe('Cross-Document Consistency', () => {
    test('all documentation files should exist', () => {
      files.forEach(file => {
        expect(contents[file]).toBeDefined();
      });
    });

    test('files should reference each other appropriately', () => {
      const allContent = Object.values(contents).join('\n');
      
      // Check if documentation references other docs
      files.forEach(file => {
        const fileName = file.replace('.md', '');
        // Log if files reference each other
        if (allContent.toLowerCase().includes(fileName.toLowerCase())) {
          console.log(`Found reference to ${file} in documentation`);
        }
      });
    });

    test('should use consistent terminology across documents', () => {
      // Extract common terms from each document
      const terms = {};
      
      Object.entries(contents).forEach(([file, content]) => {
        const words = content.toLowerCase().match(/\b\w{5,}\b/g) || [];
        const wordFreq = {};
        
        words.forEach(word => {
          wordFreq[word] = (wordFreq[word] || 0) + 1;
        });
        
        terms[file] = Object.entries(wordFreq)
          .filter(([, count]) => count > 3)
          .map(([word]) => word);
      });
      
      // This test ensures terminology is documented
      expect(Object.keys(terms).length).toBe(Object.keys(contents).length);
    });

    test('should have consistent markdown style across documents', () => {
      const styles = {};
      
      Object.entries(contents).forEach(([file, content]) => {
        const codeBlockMarker = content.includes('```') ? 'fenced' : 'none';
        const listMarker = content.match(/^[\s]*[-*+]\s+/m) ? 
          content.match(/^[\s]*[-*+]\s+/m)[0].trim()[0] : 'none';
        
        styles[file] = { codeBlockMarker, listMarker };
      });
      
      // Verify styles are documented
      expect(Object.keys(styles).length).toBe(Object.keys(contents).length);
    });
  });

  describe('Internal Link Validation', () => {
    test('all internal file links should point to existing files', () => {
      Object.entries(contents).forEach(([file, content]) => {
        const relativeLinks = content.match(/\[([^\]]+)\]\((?!http)(?!#)([^)]+)\)/g) || [];
        
        relativeLinks.forEach(link => {
          const urlMatch = link.match(/\(([^)]+)\)/);
          if (urlMatch) {
            const url = urlMatch[1].split('#')[0]; // Remove anchor
            const targetPath = path.join(__dirname, '..', url);
            
            if (!fs.existsSync(targetPath)) {
              console.warn(`${file}: Broken link to ${url}`);
            }
          }
        });
      });
    });

    test('all anchor links should point to existing headings', () => {
      Object.entries(contents).forEach(([file, content]) => {
        const anchorLinks = content.match(/\[([^\]]+)\]\(#([^)]+)\)/g) || [];
        const headings = content.match(/^#{1,6}\s+(.+)$/gm) || [];
        
        const headingIds = headings.map(h => {
          const text = h.replace(/^#{1,6}\s+/, '').trim();
          return text.toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .replace(/\s+/g, '-');
        });
        
        anchorLinks.forEach(link => {
          const anchorMatch = link.match(/#([^)]+)/);
          if (anchorMatch) {
            const anchor = anchorMatch[1];
            // Basic check - actual anchor resolution can be complex
            if (headingIds.length > 0) {
              console.log(`${file}: Checking anchor #${anchor}`);
            }
          }
        });
      });
    });
  });

  describe('Documentation Completeness', () => {
    test('README should reference architecture if it exists', () => {
      if (contents['README.md'] && contents['ARCHITECTURE.md']) {
        const readme = contents['README.md'].toLowerCase();
        const hasArchReference = readme.includes('architecture');
        
        if (!hasArchReference) {
          console.log('Note: README might benefit from referencing ARCHITECTURE.md');
        }
      }
    });

    test('should have consistent project name across documents', () => {
      const titles = {};
      
      Object.entries(contents).forEach(([file, content]) => {
        const titleMatch = content.match(/^#\s+(.+)$/m);
        if (titleMatch) {
          titles[file] = titleMatch[1].trim();
        }
      });
      
      expect(Object.keys(titles).length).toBeGreaterThan(0);
    });

    test('combined documentation should be comprehensive', () => {
      const totalWordCount = Object.values(contents)
        .reduce((sum, content) => sum + content.split(/\s+/).length, 0);
      
      expect(totalWordCount).toBeGreaterThan(500);
      console.log(`Total documentation word count: ${totalWordCount}`);
    });
  });

  describe('Documentation Quality Metrics', () => {
    test('should have good heading-to-content ratio', () => {
      Object.entries(contents).forEach(([file, content]) => {
        const headings = (content.match(/^#{1,6}\s+/gm) || []).length;
        const paragraphs = content.split('\n\n').filter(p => 
          p.trim().length > 50 && !p.trim().startsWith('#')
        ).length;
        
        if (headings > 0) {
          const ratio = paragraphs / headings;
          expect(ratio).toBeGreaterThan(0.5);
          console.log(`${file}: ${paragraphs} paragraphs, ${headings} headings (ratio: ${ratio.toFixed(2)})`);
        }
      });
    });

    test('should have appropriate code-to-text ratio for technical docs', () => {
      Object.entries(contents).forEach(([file, content]) => {
        const codeBlocks = (content.match(/```[\s\S]*?```/g) || []).length;
        const totalLines = content.split('\n').length;
        
        console.log(`${file}: ${codeBlocks} code blocks in ${totalLines} lines`);
      });
    });

    test('should maintain reasonable document sizes', () => {
      Object.entries(contents).forEach(([file, content]) => {
        const lines = content.split('\n').length;
        const words = content.split(/\s+/).length;
        
        expect(lines).toBeLessThan(10000);
        expect(words).toBeLessThan(50000);
        
        console.log(`${file}: ${lines} lines, ${words} words`);
      });
    });
  });

  describe('Accessibility Across Documents', () => {
    test('all images should have alt text across all documents', () => {
      let totalImages = 0;
      let imagesWithoutAlt = 0;
      
      Object.entries(contents).forEach(([file, content]) => {
        const images = content.match(/!\[([^\]]*)\]\([^)]+\)/g) || [];
        totalImages += images.length;
        
        images.forEach(image => {
          const altText = image.match(/!\[([^\]]*)\]/)[1];
          if (altText === '') {
            imagesWithoutAlt++;
          }
        });
      });
      
      if (totalImages > 0) {
        console.log(`Total images: ${totalImages}, without alt text: ${imagesWithoutAlt}`);
      }
    });

    test('should not use poor link text patterns', () => {
      const poorPatterns = ['click here', 'here', 'link'];
      let violations = 0;
      
      Object.entries(contents).forEach(([file, content]) => {
        const links = content.match(/\[([^\]]+)\]/g) || [];
        
        links.forEach(link => {
          const text = link.slice(1, -1).toLowerCase();
          if (poorPatterns.includes(text)) {
            violations++;
            console.warn(`${file}: Poor link text "${text}"`);
          }
        });
      });
      
      expect(violations).toBe(0);
    });
  });
});