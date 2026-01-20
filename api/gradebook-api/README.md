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

### Docker

```bash
cd /Users/cryptobroski/git/edu-ai/api/gradebook-api

# build
docker build -t gradebook-api:local .

# run (folosește .env local)
docker run --rm -p 8080:8080 --env-file .env gradebook-api:local
```
