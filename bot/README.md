npm run build
npm run dev

pm2 start dist/index.js --name edu-ai-tg-bot
pm2 restart edu-ai-tg-bot
pm2 logs edu-ai-tg-bot

