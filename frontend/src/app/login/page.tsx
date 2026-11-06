"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { apiLogin, apiRegister } from "@/lib/api/auth";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { safeNext } from "@/lib/loginLink";

/**
 * 로그인 · 회원가입.
 *
 * 공용 헤더·푸터 밖에 둔다(ConditionalShell). 로고와 '로그인 없이 계속하기'가
 * 돌아가는 길이다. `?tab=register` 로 회원가입 탭을, `?next=경로` 로 끝난 뒤
 * 돌아갈 화면을 정한다.
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
    router.push(next);
  };

  const next = safeNext(searchParams.get("next"));

  return (
    /* 홈·결과와 같은 흰 바탕 + 연회색 카드 + 보라. 제목은 지금 탭을 왜 하는지 말한다. */
    <div className="theme-violet bg-surface flex min-h-dvh items-center justify-center px-5 py-14">
      <div className="w-full max-w-[440px]">
        <Link
          href="/"
          className="text-fg mx-auto block w-fit text-[26px] font-extrabold tracking-[-0.05em]"
        >
          fides
          <i aria-hidden className="ml-0.5 inline-block size-2 -translate-y-3.5 rounded-full bg-[var(--claim-no)]" />
        </Link>

        <h1 className="text-fg mt-7 text-center text-[clamp(24px,3.2vw,30px)] leading-[1.3] font-bold tracking-[-0.03em]">
          {tab === "login" ? "다시 오셨네요" : "가입하면"}
          <br />
          <span className="text-brand-fg">
            {tab === "login" ? "내 기록을 이어서 보세요" : "기록과 북마크가 남아요"}
          </span>
        </h1>

        <div className="bg-surface-strong mt-8 rounded-[20px] p-6 md:p-7">
          <div className="bg-border/60 mb-6 flex gap-1 rounded-[12px] p-1">
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
                  "flex-1 rounded-[9px] py-2 text-sm font-semibold transition-colors",
                  tab === key ? "bg-surface text-brand-fg shadow-[var(--shadow-card)]" : "text-fg-muted hover:text-fg",
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "login" ? <LoginForm onSuccess={done} /> : <RegisterForm onSuccess={done} />}
        </div>

        {/* 분석은 로그인 없이도 된다. 막다른 길로 느껴지지 않게 나가는 길을 분명히 둔다. */}
        <p className="mt-5 text-center">
          {/* 기록 화면은 로그인이 필요해 다시 여기로 돌아오므로, 그때는 첫 화면으로 보낸다 */}
          <Link
            href={/^\/(history|dashboard)/.test(next) ? "/" : next}
            className="text-fg-muted hover:text-brand-fg text-sm font-semibold transition-colors"
          >
            로그인 없이 계속하기 →
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
      <label htmlFor={id} className="text-fg-muted text-[13px] font-semibold">
        {label}
        {hint ? <span className="text-fg-dim ml-1.5 font-normal">{hint}</span> : null}
      </label>
      {/* 홈 검색창과 같은 흰 입력칸. 포커스는 보라 테두리. */}
      <input
        id={id}
        {...props}
        className="border-border bg-surface text-fg placeholder:text-fg-dim focus:border-brand h-12 w-full rounded-[12px] border-[1.5px] px-3.5 text-[15px] outline-none transition-colors"
      />
    </div>
  );
}

function SubmitButton({ loading, children }: { loading: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="bg-brand mt-2 h-12 w-full rounded-[12px] text-[15px] font-bold text-white transition hover:brightness-110 disabled:opacity-70"
    >
      {children}
    </button>
  );
}

function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="mb-3 text-[13.5px] leading-relaxed font-semibold text-[var(--claim-no)]">
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
      <SubmitButton loading={loading}>
        {loading ? "로그인 중" : "로그인"}
      </SubmitButton>
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
      <SubmitButton loading={loading}>
        {loading ? "가입 중" : "가입하기"}
      </SubmitButton>
    </form>
  );
}
