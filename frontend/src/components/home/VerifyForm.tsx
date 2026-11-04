"use client";

import { Check, Link2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { startAnalysis } from "@/lib/api";
import { getStoredToken } from "@/lib/auth";
import { cn } from "@/lib/cn";

/**
 * 로그인 첫 화면의 주소 입력.
 *
 * 보내기 전에 여기서 거른다. 서버도 다나와가 아닌 주소는 400 으로 막지만
 * (server.py), 그 응답을 받고서야 알리면 사용자는 한 번 기다린 뒤에 실패를
 * 본다. 목록·검색 페이지처럼 `pcode` 가 없는 다나와 주소는 서버가 통과시켜
 * 분석이 시작된 뒤에 실패하므로 그것도 여기서 막는다.
 *
 * 되는 주소는 조건을 채우는 순간 알린다. 안 되는 주소는 다 치기 전에
 * 틀렸다고 하지 않도록 붙여 넣었을 때 · 입력창을 벗어날 때 · 검증하기를
 * 눌렀을 때만 알린다.
 */

const PLACEHOLDER = "다나와 상품 주소를 붙여 넣으세요";
const NOT_ALLOWED = "분석이 안 되는 주소예요.";

/** 아래 안내에서 함께 짚어 줄 칸. 0 넣을 수 있는 주소 · 1 아직 안 되는 주소 */
export type GuideCell = 0 | 1;

type Check = { ok: true; url: string } | { ok: false; message: string; cell?: GuideCell };

/** 지금까지 분석해 본 제품 중 카테고리별 하나씩 (artifacts/rescore_v2_ontology/features.csv) */
const EXAMPLES = [
  { name: "AI 세탁기", url: "https://prod.danawa.com/info/?pcode=109483526" },
  { name: "AI 공기청정기", url: "https://prod.danawa.com/info/?pcode=57505811" },
  { name: "AI 로봇청소기", url: "https://prod.danawa.com/info/?pcode=108367196" },
  { name: "AI 냉장고", url: "https://prod.danawa.com/info/?pcode=122700668" },
  { name: "AI 에어컨", url: "https://prod.danawa.com/info/?pcode=104987522" },
] as const;

export function checkDanawaUrl(raw: string): Check {
  const value = raw.trim();
  if (!value) return { ok: false, message: "다나와 상품 주소를 넣어 주세요." };
  // 틀린 곳을 콕 집고 고칠 방법을 행동으로 말한다. 'pcode' 같은 내부 용어는 쓰지 않는다.
  let u: URL;
  try {
    u = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`);
  } catch {
    return { ok: false, cell: 0, message: `${NOT_ALLOWED} 주소창의 주소를 통째로 복사해 붙여 넣어 주세요.` };
  }
  if (!/(^|\.)danawa\.com$/i.test(u.hostname)) {
    return { ok: false, cell: 1, message: `${NOT_ALLOWED} 지금은 다나와 주소만 분석할 수 있어요.` };
  }
  if (!u.searchParams.get("pcode")) {
    return {
      ok: false,
      cell: 0,
      message: `${NOT_ALLOWED} 목록이 아니라, 제품 하나를 눌러 들어간 상세 페이지 주소를 넣어 주세요.`,
    };
  }
  return { ok: true, url: u.toString() };
}

export function VerifyForm({ onGuide }: { onGuide?: (cell: GuideCell) => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = url.trim() !== "" && checkDanawaUrl(url).ok;

  function complain(value: string) {
    const checked = checkDanawaUrl(value);
    if (checked.ok || !value.trim()) return;
    setError(checked.message);
    if (checked.cell !== undefined) onGuide?.(checked.cell);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const checked = checkDanawaUrl(url);
    if (!checked.ok) {
      setError(checked.message);
      if (checked.cell !== undefined) onGuide?.(checked.cell);
      inputRef.current?.focus();
      return;
    }
    const token = getStoredToken();
    if (!token) {
      router.push("/login");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const res = await startAnalysis(checked.url, token);
      router.push(`/analysis/${res.analysis_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "분석 요청 중 오류가 발생했어요.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mx-auto mt-8 w-full max-w-[700px]">
      <div
        className={cn(
          "bg-surface flex items-center gap-3 rounded-[14px] border-[1.5px] py-1.5 pr-1.5 pl-2 shadow-[0_1px_2px_rgba(16,24,40,.04)] transition-colors",
          error ? "border-[var(--claim-no)]" : "border-border focus-within:border-brand",
        )}
      >
        <span aria-hidden className="bg-brand-soft text-brand-fg grid size-[38px] shrink-0 place-items-center rounded-[10px]">
          <Link2 size={18} />
        </span>
        <label htmlFor="verify-url" className="sr-only">
          다나와 상품 주소
        </label>
        <input
          ref={inputRef}
          id="verify-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          value={url}
          disabled={busy}
          onChange={(e) => {
            const value = e.target.value;
            setUrl(value);
            setError(null);
            const kind = (e.nativeEvent as InputEvent).inputType;
            if (kind === "insertFromPaste" || kind === "insertFromDrop") complain(value);
          }}
          onBlur={() => complain(url)}
          placeholder={PLACEHOLDER}
          className="text-fg placeholder:text-fg-dim min-w-0 flex-1 bg-transparent py-2.5 text-base outline-none"
        />
        <Check
          size={16}
          strokeWidth={3}
          aria-hidden
          className={cn(
            "text-brand-fg shrink-0 transition-all duration-200",
            valid && !busy ? "scale-100 opacity-100" : "scale-50 opacity-0",
          )}
        />
        <button
          type="submit"
          disabled={busy}
          className={cn(
            "inline-flex h-[46px] items-center gap-1.5 rounded-[10px] px-5 text-[15px] font-bold whitespace-nowrap transition-colors disabled:opacity-80",
            valid || busy ? "bg-brand text-white" : "bg-surface-strong text-fg-dim",
          )}
        >
          {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : null}
          {busy ? "시작하는 중" : "검증하기"}
        </button>
      </div>
      <p
        role="status"
        className={cn(
          "mt-2.5 min-h-[22px] text-center text-[13.5px] font-semibold",
          error ? "text-[var(--claim-no)]" : "text-brand-fg",
        )}
      >
        {error ?? (valid && !busy ? "분석할 수 있는 주소예요." : busy ? "분석을 시작하고 있어요. 곧 진행 화면으로 넘어가요." : "")}
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span className="text-fg-dim text-[13px]">예시 주소로 해 보기</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.url}
            type="button"
            disabled={busy}
            onClick={() => {
              setUrl(ex.url);
              setError(null);
              inputRef.current?.focus();
            }}
            className="border-border text-fg-muted hover:border-brand hover:bg-brand-soft hover:text-brand-fg rounded-lg border bg-surface px-3 py-1.5 text-[13px] font-bold transition-colors"
          >
            #{ex.name}
          </button>
        ))}
      </div>
    </form>
  );
}
