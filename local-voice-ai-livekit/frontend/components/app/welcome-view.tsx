import { Button } from '@/components/livekit/button';

function MicIcon() {
  return (
    <svg
      width="64"
      height="64"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="text-foreground mb-4 size-16"
    >
      <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
      <path
        d="M5 10a7 7 0 0 0 14 0"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <line
        x1="12"
        y1="19"
        x2="12"
        y2="22"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <line
        x1="9"
        y1="22"
        x2="15"
        y2="22"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref}>
      <section className="bg-background flex flex-col items-center justify-center text-center">
        <MicIcon />
        <h1 className="text-foreground text-xl font-semibold tracking-tight">Live Voice Agent</h1>
        <p className="text-muted-foreground mt-2 max-w-prose text-sm leading-6">
          Speak naturally — your words and the agent&apos;s replies appear as live transcript.
        </p>
        <Button variant="primary" size="lg" onClick={onStartCall} className="mt-6 w-64 font-mono">
          {startButtonText}
        </Button>
      </section>
    </div>
  );
};
