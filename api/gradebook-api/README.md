## gradebook-api

### Localhost

```bash
cd /root/MLDevOps/gradebook-api
npm install

# creezi .env (în același folder) pe baza env.example
cp env.example .env

npm run start
```

### PM2

```bash
cd /root/MLDevOps/gradebook-api
npm install

# creezi .env (în același folder) pe baza env.example
cp env.example .env

pm2 start ecosystem.config.cjs
pm2 save
```

