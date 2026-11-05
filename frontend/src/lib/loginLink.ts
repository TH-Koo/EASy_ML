/**
 * 로그인·회원가입으로 보냈다가 하던 화면으로 되돌아오게 하는 주소.
 * 비로그인 사용자가 북마크나 내 기록처럼 계정이 필요한 기능을 눌렀을 때 쓴다.
 */
export function loginHref(next?: string, tab: "login" | "register" = "login"): string {
  const params = new URLSearchParams();
  if (tab === "register") params.set("tab", "register");
  if (next) params.set("next", next);
  const query = params.toString();
  return query ? `/login?${query}` : "/login";
}

/**
 * `next` 는 주소창에서 누구나 고칠 수 있는 값이다. 우리 사이트 안의 경로만
 * 받는다 — `//evil.com` 이나 `https://…` 로 로그인 직후 다른 사이트로 보내는
 * 일이 없게 한다.
 */
export function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.includes("\\") ? next : "/";
}
