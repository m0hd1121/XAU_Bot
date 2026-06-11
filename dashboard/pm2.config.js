module.exports = {
  apps: [
    {
      name: 'xau-dashboard',
      script: '.next/standalone/server.js',
      cwd: '/home/botuser/xau_bot/dashboard',
      env: {
        NODE_ENV: 'production',
        PORT: '3000',
        HOSTNAME: '0.0.0.0',
        // NOTE: NEXT_PUBLIC_API_URL is baked into the JS bundle at build time
        // and cannot be changed here at runtime. Set it before running
        // deploy-dashboard.sh (or write it to .env.dashboard in the repo root).
        // This entry is kept for documentation and for tools that read pm2.config.js.
        NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8443',
      },
      max_memory_restart: '512M',
      restart_delay: 3000,
      max_restarts: 10,
      log_file: '/home/botuser/xau_bot/logs/dashboard.log',
      error_file: '/home/botuser/xau_bot/logs/dashboard-error.log',
      out_file: '/home/botuser/xau_bot/logs/dashboard-out.log',
    },
  ],
}
