import Link from "next/link";

const linkClass =
  "rounded-sm font-medium text-primary underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export default function HelpPage() {
  return (
    <div className="max-w-2xl min-w-0 space-y-8">
      <div>
        <h1 className="text-foreground text-2xl font-semibold">Help &amp; support</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          How to get started with Axonweave and where to find things.
        </p>
      </div>

      <section aria-labelledby="help-start" className="space-y-3">
        <h2 id="help-start" className="text-lg font-semibold">
          Getting started
        </h2>
        <ol className="list-decimal space-y-2 pl-5 text-sm">
          <li>
            Create a{" "}
            <Link href="/workspaces" className={linkClass}>
              workspace
            </Link>{" "}
            for each area of your learning, such as a course or a research project. A
            &quot;Personal&quot; workspace is created for you at registration.
          </li>
          <li>Inside a workspace, add subjects, then folders and chapters to organise them.</li>
          <li>
            Follow your changes on the{" "}
            <Link href="/dashboard" className={linkClass}>
              Overview
            </Link>{" "}
            and in{" "}
            <Link href="/activity" className={linkClass}>
              Recent activity
            </Link>
            .
          </li>
          <li>
            Archive things you no longer need. You can restore or permanently delete them from{" "}
            <Link href="/archived" className={linkClass}>
              Archived items
            </Link>
            .
          </li>
          <li>
            Manage your profile, password and sessions in{" "}
            <Link href="/settings" className={linkClass}>
              Settings
            </Link>
            .
          </li>
        </ol>
        <p className="text-muted-foreground text-sm">
          AI Tutor, Research Studio, Assessments and Revision are marked &quot;Coming soon&quot; in
          the sidebar. They are not available yet.
        </p>
      </section>

      <section aria-labelledby="help-email" className="space-y-3">
        <h2 id="help-email" className="text-lg font-semibold">
          Verification and password emails
        </h2>
        <p className="text-sm">
          In a local development setup, no real email is sent. Verification and password-reset
          emails are caught by Mailpit. Open{" "}
          <a
            href="http://localhost:8025"
            target="_blank"
            rel="noopener noreferrer"
            className={linkClass}
          >
            http://localhost:8025
          </a>{" "}
          to read them. This address only works on the machine running the development stack.
        </p>
        <p className="text-muted-foreground text-sm">
          Until your email is verified you can use the app, but you cannot change your email or
          password, export your data or delete your account.
        </p>
      </section>

      <section aria-labelledby="help-privacy" className="space-y-3">
        <h2 id="help-privacy" className="text-lg font-semibold">
          Privacy and your data
        </h2>
        <p className="text-sm">
          A privacy policy page has not been published yet. You can export your data or delete your
          account from{" "}
          <Link href="/settings" className={linkClass}>
            Settings
          </Link>
          .
        </p>
      </section>

      <section aria-labelledby="help-contact" className="space-y-3">
        <h2 id="help-contact" className="text-lg font-semibold">
          Contact
        </h2>
        <p className="text-sm">
          Contact support is not available yet. There is no support email, chat or ticket system in
          this version.
        </p>
      </section>
    </div>
  );
}
