const { spawn, execSync } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

// Run environment check
require('./check_env.js');

// Get the port from environment or use 10000 as default
const PORT = process.env.PORT || 10000;

// Log the port we're trying to use
console.log(`PORT environment variable: ${process.env.PORT}`);
console.log(`Using port: ${PORT}`);

// Function to start the fallback Express server
function startExpressServer() {
  console.log('Starting Express fallback server...');
  const express = require('./express-server');
}

// Check if gunicorn is available
let useGunicorn = true;
try {
  console.log('Gunicorn version:');
  console.log(execSync('gunicorn --version', { encoding: 'utf8' }));
} catch (error) {
  console.error('Gunicorn not found in PATH, falling back to Express server');
  useGunicorn = false;
  startExpressServer();
}

if (useGunicorn) {
  // Check if wsgi.py exists
  if (!fs.existsSync('wsgi.py')) {
    console.error('wsgi.py not found, falling back to Express server');
    startExpressServer();
    return;
  }

  // Start the Flask app as a child process with the correct port
  const flask = spawn('gunicorn', [
    'wsgi:app',
    '--bind', `0.0.0.0:${PORT}`,
    '--log-level', 'debug'
  ]);

  // Display Flask logs
  flask.stdout.on('data', (data) => {
    console.log(`Flask stdout: ${data}`);
  });

  flask.stderr.on('data', (data) => {
    console.error(`Flask stderr: ${data}`);
    
    // Check for specific errors that indicate we should fall back
    const output = data.toString();
    if (output.includes('No module named') || output.includes('ImportError')) {
      console.error('Flask/Gunicorn import error, falling back to Express server');
      flask.kill();
      startExpressServer();
    }
  });

  // Handle Flask exit
  flask.on('close', (code) => {
    console.log(`Flask process exited with code ${code}`);
    if (code !== 0) {
      console.log('Flask process failed, starting Express fallback server');
      startExpressServer();
    } else {
      process.exit(code);
    }
  });

  // Handle unexpected errors
  process.on('uncaughtException', (err) => {
    console.error('Uncaught exception:', err);
    flask.kill();
    startExpressServer();
  });

  // Handle termination signals
  process.on('SIGINT', () => {
    console.log('Received SIGINT, shutting down...');
    flask.kill();
    process.exit(0);
  });

  process.on('SIGTERM', () => {
    console.log('Received SIGTERM, shutting down...');
    flask.kill();
    process.exit(0);
  });

  console.log('Server started, waiting for Flask to bind...');
} else {
  console.log('Skipping Flask/Gunicorn startup, using Express server only');
} 