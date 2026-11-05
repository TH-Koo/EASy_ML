"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/primitives/Button";
import { apiLogin, apiRegister } from "@/lib/api/auth";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { safeNext } from "@/lib/loginLink";

/**
 * 로그인 · 회원가입.
 *
 * 이전에는 이 파일 안에 170줄짜리 `<style>` 블록이 있었고 자체 팔레트와
 * `'Inter'` 를 직접 참조했다. 조판을 사이트의 나머지와 맞추면서 두 가지
 * 버그도 같이 고쳤다:
 *
 *   · `<label>` 에 `htmlFor` 가 없고 입력에 `id` 가 없었다. 라벨과 입력이
 *     묶여 있지 않아 라벨을 눌러도 포커스가 가지 않고, 스크린리더가 어떤
 *     칸인지 읽어 주지 못했다. 필드 다섯 개 전부 그랬다.
 *   · `min-height: 100vh` 인데 이 라우트는 헤더·푸터가 붙는 자리였다.
 *     그래서 언제나 화면보다 길어져 스크롤이 생겼고, 화면 상단의 헤더
 *     로고와 페이지 자신의 로고가 나란히 두 번 보였다.
 *
 * 두 번째는 ConditionalShell 에서 이 라우트를 셸 밖으로 빼서 해결했다.
 * 인증 화면은 다른 데로 새어 나갈 길을 두지 않는 편이 낫고, 돌아가는
 * 길은 아래 `홈으로` 하나면 충분하다.
 */

export default function LoginPage() {
  return (
    <Suspense>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { saveUser } = useAuth();
  const [tab, setTab] = useState<"login" | "register">(
    searchParams.get("tab") === "register" ? "register" : "login",
  );

  const done = (d: { token: string; email: string; nickname: string }) => {
    saveUser(d);
    // 북마크·내 기록을 누르다 왔으면 하던 화면으로 돌려보낸다
    router.push(safeNext(searchParams.get("next")));
  };

  return (
    /* 색은 원래 화면 그대로 — 옅은 파란 글로우가 깔린 바탕, 흰 카드,
       파란 버튼. 값만 하드코딩에서 토큰으로 옮겼다. */
    <div
      className="flex min-h-dvh items-center justify-center px-5 py-16"
      style={{
        /* 은은한 브랜드 빛. 버튼과 같은 짙은 파랑을 쓴다 — 예전에는 여기만
           밝은 #1e6bff 여서 화면 전체가 하늘빛으로 떴다. */
        background:
          "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(15,53,180,.06) 0%, transparent 65%), var(--color-bg)",
      }}
    >
      <div className="w-full max-w-[420px]">
        <div className="text-center">
          <Link href="/" className="fides-wordmark text-fg text-[22px] uppercase">
            Fides
          </Link>
          <p className="text-fg-faint mt-2.5 font-mono text-xs tracking-[var(--tracking-label)] uppercase">
            AI Reliability Analysis
          </p>
        </div>

        <div className="bg-surface border-border mt-9 rounded-[var(--radius-panel)] border p-8 shadow-[var(--shadow-panel)]">
          {/* 탭 — 원래의 알약 그룹 */}
          <div className="bg-bg mb-7 flex gap-1 rounded-[var(--radius-card)] p-1">
            {(
              [
                ["login", "로그인"],
                ["register", "회원가입"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                aria-current={tab === key ? "true" : undefined}
                className={cn(
                  "flex-1 rounded-[var(--radius-input)] py-2 text-sm transition-all",
                  tab === key
                    ? "bg-surface text-fg font-medium shadow-[var(--shadow-card)]"
                    : "text-fg-dim hover:text-fg",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "login" ? (
            <LoginForm onSuccess={done} />
          ) : (
            <RegisterForm onSuccess={done} />
          )}
        </div>

        <p className="mt-6 text-center">
          <Link href="/" className="text-fg-dim hover:text-fg text-xs transition-colors">
            ← 홈으로
          </Link>
        </p>
      </div>
    </div>
  );
}

/* ── 조각 ─────────────────────────────────────────────────────────── */

function Field({
  id,
  label,
  hint,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  hint?: string;
}) {
  return (
    <div className="mb-4 flex flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-fg-dim font-mono text-xs tracking-[var(--tracking-label)] uppercase"
      >
        {label}
        {hint ? <span className="text-fg-faint ml-1.5 normal-case">{hint}</span> : null}
      </label>
      {/* 원래처럼 옅게 채운 입력칸. 포커스는 브랜드 파랑 링. */}
      <input
        id={id}
        {...props}
        className="border-border bg-surface-strong text-fg placeholder:text-fg-faint focus:border-brand focus:bg-surface focus:ring-brand/15 h-11 w-full rounded-[var(--radius-card)] border px-3.5 text-sm outline-none transition-colors focus:ring-[3px]"
      />
    </div>
  );
}

function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="alert"
      className="mb-3 border-t pt-3 text-xs leading-relaxed"
      style={{ borderColor: "var(--color-missing)", color: "var(--color-missing)" }}
    >
      {children}
    </p>
  );
}

/* ── 로그인 ───────────────────────────────────────────────────────── */

function LoginForm({
  onSuccess,
}: {
  onSuccess: (d: Awaited<ReturnType<typeof apiLogin>>) => void;
}) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const fd = new FormData(e.currentTarget);
    const email = fd.get("email") as string;
    const password = fd.get("password") as string;
    if (!email || !password) {
      setError("이메일과 비밀번호를 입력해 주세요.");
      return;
    }
    setLoading(true);
    try {
      onSuccess(await apiLogin(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Field
        id="login-email"
        name="email"
        label="이메일"
        type="email"
        placeholder="your@email.com"
        autoComplete="email"
        required
      />
      <Field
        id="login-password"
        name="password"
        label="비밀번호"
        type="password"
        placeholder="••••••••"
        autoComplete="current-password"
        required
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {/* 원래의 파란 버튼. `primary` 는 거의 검정이라 이 화면과 다르다. */}
      <Button type="submit" variant="brand" size="lg" className="mt-2 w-full" disabled={loading}>
        {loading ? "로그인 중" : "로그인"}
      </Button>
    </form>
  );
}

/* ── 회원가입 ─────────────────────────────────────────────────────── */

function RegisterForm({
  onSuccess,
}: {
  onSuccess: (d: Awaited<ReturnType<typeof apiRegister>>) => void;
}) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    const fd = new FormData(e.currentTarget);
    const email = fd.get("email") as string;
    const password = fd.get("password") as string;
    const nickname = (fd.get("nickname") as string) ?? "";
    if (!email || !password) {
      setError("이메일과 비밀번호를 입력해 주세요.");
      return;
    }
    if (password.length < 6) {
      setError("비밀번호는 6자 이상이어야 합니다.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("올바른 이메일 형식을 입력해 주세요.");
      return;
    }
    setLoading(true);
    try {
      onSuccess(await apiRegister(email, password, nickname));
    } catch (err) {
      setError(err instanceof Error ? err.message : "회원가입에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <Field
        id="register-email"
        name="email"
        label="이메일"
        type="email"
        placeholder="your@email.com"
        autoComplete="email"
        required
      />
      <Field
        id="register-nickname"
        name="nickname"
        label="닉네임"
        hint="선택"
        type="text"
        placeholder="홍길동"
        autoComplete="username"
      />
      <Field
        id="register-password"
        name="password"
        label="비밀번호"
        type="password"
        placeholder="6자 이상"
        autoComplete="new-password"
        required
      />
      {error ? <ErrorNote>{error}</ErrorNote> : null}
      {/* 원래의 파란 버튼. `primary` 는 거의 검정이라 이 화면과 다르다. */}
      <Button type="submit" variant="brand" size="lg" className="mt-2 w-full" disabled={loading}>
        {loading ? "가입 중" : "가입하기"}
      </Button>
    </form>
  );
}
