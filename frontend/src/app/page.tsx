import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard"); // (app)/dashboard — protected layout
}
