import { defineConfig } from 'vite';

export default defineConfig({
  // Relative asset URLs so the built site works from any sub-path,
  // matching the relative default ("data") of the Base data URL setting.
  base: './',
});
