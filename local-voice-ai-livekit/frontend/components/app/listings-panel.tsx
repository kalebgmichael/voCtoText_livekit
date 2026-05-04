'use client';

import { useState } from 'react';
import { useDataChannel } from '@livekit/components-react';
import { X } from '@phosphor-icons/react';

interface AirbnbListing {
  id?: string;
  url?: string;
  name?: string;
  price?: string;
  priceDetail?: string;
  rating?: string;
  badge?: string;
  screenshot?: string;
}

function parseRating(label: string | undefined): string {
  if (!label) return '';
  const match = label.match(/^([\d.]+) out of 5.*?(\d+) review/);
  if (match) return `★ ${match[1]} (${match[2]} reviews)`;
  return label;
}

export function ListingsPanel() {
  const [listings, setListings] = useState<AirbnbListing[]>([]);

  useDataChannel('listings', (msg) => {
    try {
      const text = new TextDecoder().decode(msg.payload);
      const data = JSON.parse(text);
      const items: AirbnbListing[] = Array.isArray(data) ? data : (data.listings ?? []);
      setListings(items);
    } catch {
      /* ignore malformed */
    }
  });

  useDataChannel('listing_screenshot', (msg) => {
    try {
      const text = new TextDecoder().decode(msg.payload);
      const { url, screenshot, mimeType } = JSON.parse(text);
      setListings((prev) =>
        prev.map((l) =>
          l.url === url
            ? { ...l, screenshot: `data:${mimeType ?? 'image/png'};base64,${screenshot}` }
            : l
        )
      );
    } catch {
      /* ignore malformed */
    }
  });

  if (listings.length === 0) return null;

  return (
    <aside className="fixed top-16 right-3 bottom-28 z-40 flex w-72 flex-col md:right-4 md:w-80">
      {/* Header */}
      <div className="bg-background/80 flex items-center justify-between rounded-t-xl border border-b-0 px-3 py-2 backdrop-blur-sm">
        <span className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
          {listings.length} listing{listings.length !== 1 ? 's' : ''} found
        </span>
        <button
          onClick={() => setListings([])}
          className="text-muted-foreground hover:text-foreground rounded p-0.5 transition-colors"
          aria-label="Close listings"
        >
          <X size={14} />
        </button>
      </div>

      {/* Scrollable card list */}
      <div className="bg-background/80 flex-1 overflow-y-auto overscroll-contain rounded-b-xl border backdrop-blur-sm">
        <div className="flex flex-col gap-3 p-3">
          {listings.map((listing, i) => (
            <a
              key={listing.id ?? i}
              href={listing.url ?? '#'}
              target="_blank"
              rel="noopener noreferrer"
              className="bg-card text-card-foreground hover:border-primary block overflow-hidden rounded-xl border shadow-sm transition-colors"
            >
              {listing.screenshot ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={listing.screenshot}
                  alt={listing.name ?? 'Listing preview'}
                  className="h-36 w-full object-cover object-top"
                />
              ) : null}
              <div className="space-y-1 p-3">
                {listing.badge && (
                  <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-xs font-medium">
                    {listing.badge}
                  </span>
                )}
                <p className="line-clamp-2 text-sm leading-snug font-medium">
                  {listing.name ?? 'Unnamed listing'}
                </p>
                {listing.price && <p className="text-sm font-semibold">{listing.price}</p>}
                {listing.priceDetail && (
                  <p className="text-muted-foreground line-clamp-1 text-xs">
                    {listing.priceDetail}
                  </p>
                )}
                {listing.rating && (
                  <p className="text-muted-foreground text-xs">{parseRating(listing.rating)}</p>
                )}
              </div>
            </a>
          ))}
        </div>
      </div>
    </aside>
  );
}
