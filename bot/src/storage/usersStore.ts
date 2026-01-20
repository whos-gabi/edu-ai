import { promises as fs } from "node:fs";
import path from "node:path";
import { StoredUser } from "../types.js";

const USERS_FILE = (() => {
  const raw = process.env.USERS_FILE?.trim();
  if (!raw) return path.join(process.cwd(), "users.json");
  return path.isAbsolute(raw) ? raw : path.resolve(process.cwd(), raw);
})();

async function ensureUsersFile(): Promise<void> {
  await fs.mkdir(path.dirname(USERS_FILE), { recursive: true });
  try {
    await fs.access(USERS_FILE);
  } catch {
    await fs.writeFile(USERS_FILE, "[]\n", "utf8");
  }
}

export async function readAllUsers(): Promise<StoredUser[]> {
  await ensureUsersFile();
  const raw = await fs.readFile(USERS_FILE, "utf8");
  const parsed = JSON.parse(raw) as unknown;
  if (!Array.isArray(parsed)) return [];
  return parsed as StoredUser[];
}

async function writeAllUsers(users: StoredUser[]): Promise<void> {
  await ensureUsersFile();
  const tmp = `${USERS_FILE}.tmp`;
  await fs.writeFile(tmp, JSON.stringify(users, null, 2) + "\n", "utf8");
  await fs.rename(tmp, USERS_FILE);
}

export async function upsertUser(next: StoredUser): Promise<void> {
  const users = await readAllUsers();
  const idx = users.findIndex((u) => u.telegramId === next.telegramId);
  if (idx >= 0) users[idx] = next;
  else users.push(next);
  await writeAllUsers(users);
}

export async function findUserByTelegramId(
  telegramId: number
): Promise<StoredUser | undefined> {
  const users = await readAllUsers();
  return users.find((u) => u.telegramId === telegramId);
}

