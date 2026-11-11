"use client";

import { useParams } from "next/navigation";
import { MaterialPage } from "@/features/study/material-page";

export default function StudyMaterialPage() {
  const { materialId } = useParams<{ materialId: string }>();
  return <MaterialPage materialId={materialId} />;
}
