"use client";

import { Suspense } from "react";
import { LoadingSpinner } from "@/components/ui/loading";
import { StudyRoom } from "@/features/study-room/study-room";

export default function StudyRoomPage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <LoadingSpinner />
        </div>
      }
    >
      <StudyRoom />
    </Suspense>
  );
}
