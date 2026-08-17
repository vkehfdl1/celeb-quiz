module.exports = {
  apps: [
    {
      name: 'celeb-quiz-admin',
      script: './scripts/admin_server.py',
      interpreter: 'python3',
      args: '--port 8765',
      cwd: '/Users/jeffrey/Projects/celeb-quiz',
      exec_mode: 'fork',
      instances: 1,
      autorestart: true,
      watch: false,
    },
    {
      name: 'celeb-quiz-tunnel',
      script: 'cloudflared',
      args: '--config /Users/jeffrey/Projects/celeb-quiz/cloudflared.yml tunnel run',
      cwd: '/Users/jeffrey/Projects/celeb-quiz',
      exec_mode: 'fork',
      instances: 1,
      autorestart: true,
      watch: false,
    },
  ],
};
