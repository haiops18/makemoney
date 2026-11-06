import { FormEvent, useState } from "react";
import { Languages, Moon, ShieldCheck, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { rememberedUsername, type OwnerSession } from "./session";

const apiBase = import.meta.env.VITE_API_BASE_URL || "";
const loginSchema = z.object({ access_token: z.string(), token_type: z.literal("bearer"), expires_in: z.number().int().positive() });

type Props = { dark: boolean; toggleTheme: () => void; onLogin: (session: OwnerSession, remember: boolean) => void };

/** Full-screen Owner sign-in. Submitting the form (Enter in any field) signs in. */
export default function Login({ dark, toggleTheme, onLogin }: Props) {
  const { t, i18n } = useTranslation();
  const initialUser = rememberedUsername();
  const [username, setUsername] = useState(initialUser);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(!!initialUser);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password || busy) { setError(t("auth.required")); return; }
    setError(null); setBusy(true);
    const controller = new AbortController(); const timeout = window.setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/login`, { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: username.trim(), password }) });
      if (response.status === 401) { setError(t("auth.invalid")); return; }
      if (!response.ok) { setError(t("auth.unavailable")); return; }
      const session = loginSchema.parse(await response.json());
      setPassword("");
      onLogin({ token: session.access_token, expiresAt: Date.now() + session.expires_in * 1000, username: username.trim() }, remember);
    } catch {
      setError(t("auth.unavailable"));
    } finally {
      window.clearTimeout(timeout); setBusy(false);
    }
  }

  return <div className={dark ? "app login-page dark" : "app login-page"}>
    <div className="login-tools">
      <button type="button" aria-label={t("shell.language")} onClick={() => void i18n.changeLanguage(i18n.language === "vi" ? "en" : "vi")}><Languages size={16}/>{i18n.language.toUpperCase()}</button>
      <button type="button" aria-label={t("shell.theme")} onClick={toggleTheme}>{dark ? <Sun size={16}/> : <Moon size={16}/>}</button>
    </div>
    <main className="login-card">
      <div className="brand"><ShieldCheck/> <span>AUTO MONEY <b>AI</b></span></div>
      <h1>{t("auth.title")}</h1>
      <p className="muted">{t("auth.body")}</p>
      <form onSubmit={submit} noValidate>
        <label className="field">{t("auth.username")}<input aria-label={t("auth.username")} name="username" autoComplete="username" autoFocus={!initialUser} value={username} onChange={event => setUsername(event.target.value)} disabled={busy}/></label>
        <label className="field">{t("auth.password")}<input aria-label={t("auth.password")} name="password" type="password" autoComplete="current-password" autoFocus={!!initialUser} value={password} onChange={event => setPassword(event.target.value)} disabled={busy}/></label>
        <label className="login-remember"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)} disabled={busy}/>{t("auth.remember")}</label>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary" type="submit" disabled={busy}>{busy ? t("auth.signingIn") : t("auth.login")}</button>
      </form>
      <p className="login-note">{t("auth.note")}</p>
    </main>
  </div>;
}
