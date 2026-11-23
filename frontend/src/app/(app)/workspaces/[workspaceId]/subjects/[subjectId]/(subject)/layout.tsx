import { EnvironmentShell } from "@/features/learning-spaces/environment-shell";

/** Learning environment chrome: where-am-I trail, header, quick actions and the tool tabs. */
export default function EnvironmentLayout({ children }: { children: React.ReactNode }) {
  return <EnvironmentShell>{children}</EnvironmentShell>;
}
