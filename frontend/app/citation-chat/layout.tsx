import type { ReactNode } from "react";
import { Toaster } from "sonner";

export default function CitationChatLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      {children}
      <Toaster closeButton position="top-right" richColors />
    </>
  );
}
