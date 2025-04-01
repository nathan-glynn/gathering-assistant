const express = require('express');
const app = express();
const PORT = process.env.PORT || 10000;

// Basic health check endpoint
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    port: PORT,
    env: process.env.NODE_ENV,
    message: 'Express server is running properly.'
  });
});

// Root endpoint
app.get('/', (req, res) => {
  res.send(`
    <html>
      <head>
        <title>Gathering Assistant</title>
        <style>
          body { font-family: Arial, sans-serif; margin: 40px; }
          h1 { color: #333; }
          .status { padding: 20px; background: #f0f0f0; border-radius: 5px; }
        </style>
      </head>
      <body>
        <h1>Gathering Assistant</h1>
        <div class="status">
          <p>The Express fallback server is running on port ${PORT}.</p>
          <p>The Flask application is not accessible. Please check the logs for more information.</p>
        </div>
      </body>
    </html>
  `);
});

// Start the server
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Express server listening on port ${PORT}`);
}); 