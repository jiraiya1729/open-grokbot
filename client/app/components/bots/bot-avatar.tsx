import type { Bot } from "@/lib/types";

type BotAvatarProps = {
  bot: Pick<Bot, "name" | "avatar_value" | "presence">;
  size?: "small" | "medium" | "large";
  active?: boolean;
};

function avatarVariant(name: string) {
  return Array.from(name).reduce((sum, character) => sum + character.charCodeAt(0), 0) % 4;
}

export function BotAvatar({ bot, size = "medium", active = false }: BotAvatarProps) {
  return (
    <span
      className={`bot-avatar bot-avatar-${size} ${active ? "is-active" : ""}`}
      data-variant={avatarVariant(bot.name)}
      aria-label={`${bot.name} · ${active ? "working" : bot.presence}`}
      role="img"
    >
      <span className="bot-face" aria-hidden="true">
        <i className="eye eye-left" />
        <i className="eye eye-right" />
        <i className="mouth" />
        <b>{bot.avatar_value || "✦"}</b>
      </span>
      <span className={`avatar-state ${active ? "working" : bot.presence}`} aria-hidden="true" />
    </span>
  );
}
