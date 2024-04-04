// ecosystem.config.js
module.exports = {
  apps: [
    {
      name: 'main',
      script: './venv/bin/python',
      args: 'main.py',
      watch: true,
      interpreter: 'none',
      env: {
        NODE_ENV: 'development',
      },
      env_production: {
        NODE_ENV: 'production',
      },
      log: {
        max_size: '1G'
      }
    }
  ]
};

  