export type AuthStage = "await_phone" | "await_code" | "authenticated";

export type StoredUser = {
  telegramId: number;
  username?: string;
  firstName?: string;
  lastName?: string;

  phoneNumber?: string;
  authStage: AuthStage;

  createdAt: string;
  updatedAt: string;
};

