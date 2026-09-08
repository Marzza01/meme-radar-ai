module.exports = {
  apps: [
    {
      name: "meme-radar-engine",
      script: "src/convergence_engine.py",
      interpreter: "python",
      autorestart: true,
      max_restarts: 50,
      restart_delay: 5000,
      watch: false,
      max_memory_restart: "1G",
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      }
    },
    {
      name: "meme-radar-dashboard",
      script: "src/dashboard/server.py",
      interpreter: "python",
      autorestart: true,
      max_restarts: 50,
      restart_delay: 3000,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      }
    }
  ]
};
