'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { useDataChannel, useSessionContext, useSessionMessages } from '@livekit/components-react';
import type { AppConfig } from '@/app-config';
import { ChatTranscript } from '@/components/app/chat-transcript';
import { ListingsPanel } from '@/components/app/listings-panel';
import { PreConnectMessage } from '@/components/app/preconnect-message';
import { TileLayout } from '@/components/app/tile-layout';
import {
  AgentControlBar,
  type ControlBarControls,
} from '@/components/livekit/agent-control-bar/agent-control-bar';
import { cn } from '@/lib/utils';
import { ScrollArea } from '../livekit/scroll-area/scroll-area';

const MotionBottom = motion.create('div');

const BOTTOM_VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
      translateY: '0%',
    },
    hidden: {
      opacity: 0,
      translateY: '100%',
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    delay: 0.5,
    ease: 'easeOut',
  },
};

interface FadeProps {
  top?: boolean;
  bottom?: boolean;
  className?: string;
}

export function Fade({ top = false, bottom = false, className }: FadeProps) {
  return (
    <div
      className={cn(
        'from-background pointer-events-none h-4 bg-linear-to-b to-transparent',
        top && 'bg-linear-to-b',
        bottom && 'bg-linear-to-t',
        className
      )}
    />
  );
}

interface SessionViewProps {
  appConfig: AppConfig;
}

interface ScreenshotItem {
  url: string;
  src: string;
  index: number;
}

interface GeneralScreenshot {
  url: string;
  src: string;
}

export const SessionView = ({
  appConfig,
  ...props
}: React.ComponentProps<'section'> & SessionViewProps) => {
  const session = useSessionContext();
  const { messages } = useSessionMessages(session);
  const chatOpen = true;
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const [detailScreenshots, setDetailScreenshots] = useState<ScreenshotItem[]>([]);
  const [generalScreenshots, setGeneralScreenshots] = useState<GeneralScreenshot[]>([]);

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: true,
    camera: false,
    screenShare: false,
  };

  useDataChannel('open_url', (msg) => {
    try {
      const { url } = JSON.parse(new TextDecoder().decode(msg.payload));
      if (url) {
        const normalized = /^https?:\/\//i.test(url) ? url : `https://${url}`;
        window.open(normalized, '_blank', 'noopener,noreferrer');
      }
    } catch {
      /* ignore */
    }
  });

  useDataChannel('listings', () => {
    setDetailScreenshots([]);
  });

  useDataChannel('screenshot', (msg) => {
    try {
      const { url, screenshot, mimeType } = JSON.parse(new TextDecoder().decode(msg.payload));
      const src = `data:${mimeType ?? 'image/jpeg'};base64,${screenshot}`;
      setGeneralScreenshots((prev) => [...prev, { url, src }]);
      setTimeout(() => {
        if (scrollAreaRef.current) {
          scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
        }
      }, 100);
    } catch {
      /* ignore */
    }
  });

  useDataChannel('listing_screenshot_clear', () => {
    setDetailScreenshots([]);
  });

  useDataChannel('listing_screenshot', (msg) => {
    try {
      const { url, screenshot, mimeType } = JSON.parse(new TextDecoder().decode(msg.payload));
      const src = `data:${mimeType ?? 'image/png'};base64,${screenshot}`;
      setDetailScreenshots((prev) => {
        const idx = prev.findIndex((s) => s.url === url);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = { ...next[idx], src };
          return next;
        }
        return [...prev, { url, src, index: prev.length + 1 }];
      });
      setTimeout(() => {
        if (scrollAreaRef.current) {
          scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
        }
      }, 100);
    } catch {
      /* ignore */
    }
  });

  useEffect(() => {
    const lastMessage = messages.at(-1);
    const lastMessageIsLocal = lastMessage?.from?.isLocal === true;

    if (scrollAreaRef.current && lastMessageIsLocal) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);

  return (
    <section className="bg-background relative z-10 h-full w-full overflow-hidden" {...props}>
      {/* Chat Transcript */}
      <div
        className={cn(
          'fixed inset-0 grid grid-cols-1 grid-rows-1',
          !chatOpen && 'pointer-events-none'
        )}
      >
        <Fade top className="absolute inset-x-4 top-0 h-40" />
        <ScrollArea ref={scrollAreaRef} className="px-4 pt-40 pb-[150px] md:px-6 md:pb-[200px]">
          <ChatTranscript
            hidden={!chatOpen}
            messages={messages}
            className="mx-auto max-w-2xl space-y-3 transition-opacity duration-300 ease-out"
          />
          {detailScreenshots.length > 0 && (
            <div className="mx-auto mt-4 max-w-2xl space-y-4">
              <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Listing Details &mdash; {detailScreenshots.length} page
                {detailScreenshots.length !== 1 ? 's' : ''}
              </p>
              {detailScreenshots.map((shot) => {
                let domain = shot.url;
                try {
                  domain = new URL(shot.url).hostname.replace('www.', '');
                } catch {
                  /* keep original */
                }
                return (
                  <a
                    key={shot.url}
                    href={shot.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-card text-card-foreground hover:border-primary block overflow-hidden rounded-xl border shadow-sm transition-colors"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={shot.src}
                      alt={`Listing ${shot.index} screenshot`}
                      className="w-full object-cover object-top"
                    />
                    <div className="text-muted-foreground px-3 py-2 text-xs">
                      Listing {shot.index} &middot; {domain}
                    </div>
                  </a>
                );
              })}
            </div>
          )}
          {generalScreenshots.length > 0 && (
            <div className="mx-auto mt-4 max-w-2xl space-y-4">
              <p className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Screenshots
              </p>
              {generalScreenshots.map((shot, i) => {
                let domain = shot.url;
                try {
                  domain = new URL(shot.url).hostname.replace('www.', '');
                } catch {
                  /* keep original */
                }
                return (
                  <a
                    key={`${shot.url}-${i}`}
                    href={shot.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="bg-card text-card-foreground hover:border-primary block overflow-hidden rounded-xl border shadow-sm transition-colors"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={shot.src}
                      alt={`Screenshot of ${domain}`}
                      className="w-full object-cover object-top"
                    />
                    <div className="text-muted-foreground px-3 py-2 text-xs">{domain}</div>
                  </a>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Tile Layout */}
      <TileLayout chatOpen={chatOpen} />

      {/* Listings panel — populated via data channel when agent calls search_accommodations */}
      <ListingsPanel />

      {/* Bottom */}
      <MotionBottom
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="fixed inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {appConfig.isPreConnectBufferEnabled && (
          <PreConnectMessage messages={messages} className="pb-4" />
        )}
        <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
          <Fade bottom className="absolute inset-x-0 top-0 h-4 -translate-y-full" />
          <AgentControlBar
            controls={controls}
            isConnected={session.isConnected}
            onDisconnect={session.end}
          />
        </div>
      </MotionBottom>
    </section>
  );
};
