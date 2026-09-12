import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

export default defineConfig({
  plugins: [
    react(),
    // Inline CSS and JS into one self-contained index.html.
    //
    // Without this the build emits `<script type="module" src=...>`, and a
    // module script FETCHES its source — which Chromium blocks from a file://
    // origin (opaque origin, CORS). The page would therefore render blank when
    // opened from disk, which is precisely the scenario NFR-1 exists to cover.
    // An inline script has nothing to fetch, so it just runs.
    //
    // Bonus: the deliverable becomes a single ~2 MB HTML file that can be
    // emailed or carried on a USB stick with no build step and no server.
    viteSingleFile(),
  ],

  // Relative asset paths so the built page opens straight from file://
  // with no server. This is NFR-1 and it is pass/fail for the demo.
  base: './',

  // No publicDir: the fourteen baked files are imported and bundled by src/data.ts
  // instead of fetched, because fetch() is blocked from a file:// origin and
  // NFR-1 requires the built page to work straight from disk. See src/data.ts.
  publicDir: false,

  server: {
    // src/data.ts imports from ../web/data, which sits outside the Vite root.
    fs: { allow: ['..'] },
  },

  build: {
    outDir: 'dist',
    // MapLibre is large; the warning is noise at this size.
    chunkSizeWarningLimit: 1200,
  },
})
