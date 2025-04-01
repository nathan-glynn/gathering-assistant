const { spawn, execSync } = require('child_process');
const fs = require('fs');

// Get the port from environment or use 10000 as default
const PORT = process.env.PORT || 10000;

console.log(`Starting server on port ${PORT}`);

// Create a very basic server to show we're binding to the port
const http = require('http');
const server = http.createServer((req, res) => {
  if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', port: PORT }));
  } else {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end(`
      <html>
        <head><title>Gathering Assistant</title></head>
        <body>
          <h1>Gathering Assistant</h1>
          <p>The server is running on port ${PORT}</p>
          <p>Add /health to the URL to see the health check</p>
        </body>
      </html>
    `);
  }
});

// IMPORTANT: Explicitly listen on the PORT with 0.0.0.0
server.listen(PORT, '0.0.0.0', () => {
  console.log(`HTTP server listening on port ${PORT}`);
});

// Now try to start the Flask app
try {
  console.log('Attempting to start Flask app with gunicorn...');
  // For now, we're just binding to the port, which is what Render needs
  // We'll implement the Flask integration after confirming this works
} catch (error) {
  console.error('Error starting Flask app:', error);
} 