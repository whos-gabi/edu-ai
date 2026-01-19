module.exports = {
  apps: [
    {
      name: "gradebook-api",
      cwd: __dirname,
      script: "src/index.js",
      instances: 1,
      exec_mode: "fork",
      env_file: ".env",
      env: {
        NODE_ENV: "production"
      }
    }
  ]
};

