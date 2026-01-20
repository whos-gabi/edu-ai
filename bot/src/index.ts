import "dotenv/config";
import { Telegraf } from "telegraf";
import { agentReply } from "./agent/agentClient.js";
import { getStudentByPhone } from "./gradebook/gradebookClient.js";
import { findUserByTelegramId, upsertUser } from "./storage/usersStore.js";
import { StoredUser } from "./types.js";

function nowIso(): string {
  return new Date().toISOString();
}

function displayName(u: StoredUser): string {
  const name = [u.firstName, u.lastName].filter(Boolean).join(" ").trim();
  return name || u.username || "there";
}

function normalizePhone(input: string): string {
  return input.trim();
}

function isValidRomanianPhone(input: string): boolean {
  // Strict format: +40 followed by 9 digits (ex: +40722522446)
  return /^\+40\d{9}$/.test(input.trim());
}

function isSixDigitCode(input: string): boolean {
  return /^\d{6}$/.test(input.trim());
}

function requireFrom(ctx: any) {
  const from = ctx.from;
  if (!from?.id) return undefined;
  return from as {
    id: number;
    username?: string;
    first_name?: string;
    last_name?: string;
  };
}

async function getUserEnsuringStored(ctx: any): Promise<StoredUser | undefined> {
  const from = requireFrom(ctx);
  if (!from) return undefined;

  const existing = await findUserByTelegramId(from.id);
  if (existing) return existing;

  const created: StoredUser = {
    telegramId: from.id,
    username: from.username,
    // Will be overwritten with the Gradebook student name after phone verification
    firstName: undefined,
    lastName: undefined,
    phoneNumber: undefined,
    authStage: "await_phone",
    createdAt: nowIso(),
    updatedAt: nowIso(),
  };

  await upsertUser(created);
  return created;
}

async function saveUserPatch(user: StoredUser, patch: Partial<StoredUser>) {
  const next: StoredUser = {
    ...user,
    ...patch,
    updatedAt: nowIso(),
  };
  await upsertUser(next);
  return next;
}

const token = process.env.BOT_TOKEN;
if (!token) {
  console.error("Missing BOT_TOKEN in environment.");
  process.exit(1);
}

const bot = new Telegraf(token);

bot.start(async (ctx) => {
  const user = await getUserEnsuringStored(ctx);
  if (!user) return;

  if (user.authStage === "authenticated") {
    await ctx.reply("You already started.");
    return;
  }

  if (user.authStage === "await_code") {
    await ctx.reply("send comfirmation code send on phone number (6 digits)");
    return;
  }

  await ctx.reply("Hello please authenticate with your number:");
});

bot.command("logout", async (ctx) => {
  const user = await getUserEnsuringStored(ctx);
  if (!user) return;

  if (user.authStage !== "authenticated") {
    await ctx.reply("Warning: you are already logged out.");
    return;
  }

  await saveUserPatch(user, {
    authStage: "await_phone",
    phoneNumber: undefined,
  });

  await ctx.reply("Logged out. Hello please authenticate with your number:");
});

bot.on("text", async (ctx) => {
  const text = ctx.message?.text?.trim() ?? "";
  if (!text) return;
  if (text.startsWith("/")) return;

  const user = await getUserEnsuringStored(ctx);
  if (!user) return;

  if (user.authStage === "await_phone") {
    const phoneNumber = normalizePhone(text);
    if (!isValidRomanianPhone(phoneNumber)) {
      await ctx.reply('Please send phone number in this format: "+40722522446"');
      return;
    }

    const apiKey = process.env.GRADEBOOK_API_KEY;
    if (!apiKey) {
      await ctx.reply("Server misconfigured: missing GRADEBOOK_API_KEY.");
      return;
    }

    let lookup;
    try {
      lookup = await getStudentByPhone(phoneNumber, apiKey);
    } catch (err) {
      console.error(err);
      await ctx.reply("Verification failed. Please try again.");
      return;
    }

    if (!lookup) {
      await ctx.reply(
        "This phone number was not found in the gradebook. Please send a valid student number."
      );
      return;
    }

    await saveUserPatch(user, {
      phoneNumber: lookup.student.phoneNumber,
      firstName: lookup.student.firstName,
      lastName: lookup.student.lastName,
      authStage: "await_code",
    });
    await ctx.reply("send comfirmation code send on phone number (6 digits)");
    return;
  }

  if (user.authStage === "await_code") {
    if (!isSixDigitCode(text)) {
      await ctx.reply("Please send a 6 digit code.");
      return;
    }

    const next = await saveUserPatch(user, { authStage: "authenticated" });
    await ctx.reply(
      `hello ${displayName(next)} i will be you Edu AI assistant, you can ask me any thing about grades or learning methodology`
    );
    return;
  }

  // #region debug log H6
  fetch("http://127.0.0.1:7242/ingest/6f0a844a-d53d-4ddc-b246-3444195ce1ea", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sessionId: "debug-session",
      runId: "pre-fix",
      hypothesisId: "H6",
      location: "index.ts:bot_text",
      message: "agent_reply_request",
      data: {
        auth_stage: user.authStage,
        has_phone: Boolean(user.phoneNumber),
        phone_len: user.phoneNumber?.length ?? 0,
        phone_kind: user.phoneNumber?.startsWith("+")
          ? "phone_like"
          : user.phoneNumber?.match(/^[0-9]+$/)
          ? "digits_only"
          : "other",
        agent_url_present: Boolean(process.env.AGENT_API_URL?.trim()),
      },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion

  if (!user.phoneNumber) {
    await ctx.reply("Missing verified phone number. Please /logout and try again.");
    return;
  }

  const reply = await agentReply(text, {
    url: process.env.AGENT_API_URL,
    apiKey: process.env.AGENT_API_KEY,
    phone: user.phoneNumber,
  });
  await ctx.reply(reply);
});

bot.catch((err) => {
  console.error("Bot error:", err);
});

process.once("SIGINT", () => bot.stop("SIGINT"));
process.once("SIGTERM", () => bot.stop("SIGTERM"));

try {
  await bot.telegram.setMyCommands([
    { command: "start", description: "Start / authenticate" },
    { command: "logout", description: "Logout" },
  ]);
} catch (err) {
  console.error("Failed to set bot commands:", err);
}

await bot.launch();
console.log("Bot started.");

