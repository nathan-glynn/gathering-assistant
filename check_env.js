console.log('Checking environment variables:');
console.log(`PORT: ${process.env.PORT}`);
console.log(`FLASK_ENV: ${process.env.FLASK_ENV}`);
console.log(`NODE_ENV: ${process.env.NODE_ENV}`);
console.log(`FLASK_DEBUG: ${process.env.FLASK_DEBUG}`);
console.log(`PERPLEXITY_API_KEY present: ${Boolean(process.env.PERPLEXITY_API_KEY)}`);
console.log(`Current working directory: ${process.cwd()}`);
console.log('File listing:');
require('child_process').execSync('ls -la', { encoding: 'utf8' }); 