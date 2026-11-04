"use client";

import { AlertTriangle, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { PipelineProgress } from "@/components/analysis/PipelineProgress";
import { Button } from "@/components/primitives/Button";
import { ResultView } from "@/components/result/ResultView";
import { fetchProgress, fetchResult, openProgressStream } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import type { AnalysisResult, ProgressEvent } from "@/types/analysis";

type Phase = "bootstrapping" | "running" | "complete" | "error";

interface AnalysisRunnerProps {
  id: string;
}

export function AnalysisRunner({ id }: AnalysisRunnerProps) {
  const [phase, setPhase] = useState<Phase>("bootstrapping");
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  /* 초기값은 0 이다. 아래 effect 가 마운트 직후 바로 덮어쓰므로 여기서
     Date.now() 를 부를 이유가 없고, 렌더 중 호출은 규칙 위반이다. */
  const startRef = useRef<number>(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Timer: start on mount, stop when complete/error
  useEffect(() => {
    startRef.current = Date.now();
    timerRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Stop timer when done
  useEffect(() => {
    if (phase === "complete" || phase === "error") {
      if (timerRef.current) clearInterval(timerRef.current);
    }
  }, [phase]);

  // 1) On mount, try the final result first. If 200, the job is already done
  //    (refresh-safe). If 404/409, switch to streaming.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await fetchResult(id);
        if (!alive) return;
        setResult(r);
        setPhase("complete");
      } catch (err) {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 404) {
          setErrorMessage(
            "해당 분석을 찾을 수 없습니다. URL을 다시 확인해 주세요.",
          );
          setPhase("error");
          return;
        }
        // 409 (not yet completed) or any other error → stream progress.
        try {
          const snap = await fetchProgress(id);
          if (alive) setProgress(snap);
        } catch {
          // Snapshot can fail (e.g. server starting); the stream will recover.
        }
        if (alive) setPhase("running");
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  // 2) While running, open the SSE stream.
  useEffect(() => {
    if (phase !== "running") return;
    const close = openProgressStream(id, {
      onProgress: (ev) => setProgress(ev),
      onComplete: async () => {
        try {
          const r = await fetchResult(id);
          setResult(r);
          setPhase("complete");
        } catch (err) {
          setErrorMessage(
            err instanceof ApiError
              ? err.message
              : "결과를 불러올 수 없습니다.",
          );
          setPhase("error");
        }
      },
      onError: (streamErr) => {
        if (streamErr.kind === "server") {
          setProgress(streamErr.event);
          const firstError = streamErr.event.stages?.find(
            (s) => s.state === "error",
          );
          setErrorMessage(
            firstError?.error_message ?? "분석 도중 오류가 발생했습니다.",
          );
          setPhase("error");
        } else {
          setErrorMessage(
            "실시간 연결이 끊겼습니다. 페이지를 새로고침해 주세요.",
          );
        }
      },
    });
    return close;
  }, [phase, id]);

  if (phase === "error") {
    return <ErrorPanel message={errorMessage ?? "알 수 없는 오류가 발생했습니다."} />;
  }
  if (phase === "complete" && result) {
    return <ResultView data={result} elapsedSeconds={elapsed} />;
  }
  return <PipelineProgress progress={progress} />;
}

/**
 * 실패 화면.
 *
 * 진행 화면과 같은 흰 바탕·가운데 제목을 쓰고, 문제를 뜻하는 로즈 하나만
 * 얹는다. 할 수 있는 일은 다른 제품을 다시 검색하는 것 하나다.
 */
function ErrorPanel({ message }: { message: string }) {
  return (
    <section className="theme-violet bg-surface flex flex-1 justify-center px-5 pt-16 pb-20 md:pt-20">
      <div className="w-full max-w-[560px] text-center">
        <span
          aria-hidden
          className="mx-auto grid size-11 place-items-center rounded-full bg-[var(--claim-no-soft)] text-[var(--claim-no)]"
        >
          <AlertTriangle size={20} />
        </span>
        <h1 className="text-fg mt-5 text-[clamp(24px,3.2vw,30px)] leading-snug font-bold tracking-[-0.03em]">
          분석을 끝내지 못했어요
        </h1>
        <p className="text-fg-muted mt-3 text-[15px] leading-relaxed">{message}</p>
        <div className="mt-8 flex justify-center">
          <Button asChild variant="cta" size="lg" style={{ background: "var(--color-brand)" }}>
            <Link href="/">
              <Search size={16} aria-hidden />
              다른 제품 검색하기
            </Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
