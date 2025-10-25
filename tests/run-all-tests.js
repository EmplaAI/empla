const { execSync } = require('child_process');
const path = require('path');

console.log('================================');
console.log('Running Comprehensive Test Suite');
console.log('================================\n');

try {
  // Run Jest tests
  console.log('📋 Running Jest unit tests...\n');
  execSync('npm test -- --verbose', { stdio: 'inherit' });
  
  console.log('\n✅ All Jest tests passed!\n');
  
  // Run link validation
  console.log('🔗 Running link validation...\n');
  execSync('node tests/validate-links.js', { stdio: 'inherit' });
  
  console.log('\n================================');
  console.log('✅ All tests completed successfully!');
  console.log('================================\n');
  
} catch (error) {
  console.error('\n❌ Tests failed!');
  process.exit(1);
}