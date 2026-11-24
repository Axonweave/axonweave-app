import { api } from "./client";
import type { components } from "@/types/api.generated";

type S = components["schemas"];
export type Preset = S["PresetOut"];
export type PresetInput = S["PresetIn"];

const enc = encodeURIComponent;

export const presetsApi = {
  list: () => api.get<Preset[]>("/study/presets").then((r) => r.data),
  create: (body: PresetInput) => api.post<Preset>("/study/presets", body).then((r) => r.data),
  replace: (id: string, body: PresetInput) =>
    api.put<Preset>(`/study/presets/${enc(id)}`, body).then((r) => r.data),
  makeDefault: (id: string) =>
    api.post<Preset>(`/study/presets/${enc(id)}/default`).then((r) => r.data),
  remove: (id: string) => api.delete<void>(`/study/presets/${enc(id)}`),
};
