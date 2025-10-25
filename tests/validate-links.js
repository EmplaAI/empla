const fs = require('fs');
const path = require('path');

const files = ['ARCHITECTURE.md', 'CLAUDE.md', 'README.md'];

console.log('Validating links in markdown files...\n');

files.forEach(file => {
  const filePath = path.join(__dirname, '..', file);
  
  if (!fs.existsSync(filePath)) {
    console.log(`⚠️  ${file}: File not found`);
    return;
  }
  
  const content = fs.readFileSync(filePath, 'utf8');
  
  // Extract all links
  const linkPattern = /\[([^\]]+)\]\(([^)]+)\)/g;
  const links = [];
  let match;
  
  while ((match = linkPattern.exec(content)) !== null) {
    links.push({
      text: match[1],
      url: match[2],
      line: content.substring(0, match.index).split('\n').length
    });
  }
  
  console.log(`📄 ${file}:`);
  console.log(`   Found ${links.length} links`);
  
  // Categorize links
  const internalLinks = links.filter(l => l.url.startsWith('#'));
  const externalLinks = links.filter(l => l.url.startsWith('http'));
  const relativeLinks = links.filter(l => !l.url.startsWith('#') && !l.url.startsWith('http'));
  
  console.log(`   - Internal anchor links: ${internalLinks.length}`);
  console.log(`   - External links: ${externalLinks.length}`);
  console.log(`   - Relative file links: ${relativeLinks.length}`);
  
  // Validate relative file links exist
  relativeLinks.forEach(link => {
    const targetPath = path.join(__dirname, '..', link.url.split('#')[0]);
    if (!fs.existsSync(targetPath)) {
      console.log(`   ⚠️  Line ${link.line}: Broken relative link: ${link.url}`);
    }
  });
  
  // Check for potential issues
  if (links.some(l => l.url.includes(' '))) {
    console.log(`   ⚠️  Warning: Some links contain spaces (should be encoded)`);
  }
  
  console.log('');
});

console.log('✅ Link validation complete');