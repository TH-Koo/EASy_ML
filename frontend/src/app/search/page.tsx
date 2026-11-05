import { redirect } from "next/navigation";

/** 검색 화면은 이제 첫 화면(/)이다. 이미 공유된 /search 링크를 위해 남겨 둔다. */
export default function SearchPage() {
  redirect("/");
}
