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
