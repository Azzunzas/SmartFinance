import { defineConfig } from 'orval';

export default defineConfig({
  smartfinance: {
    input: './openapi.json',
    output: {
      mode: 'tags-split',
      target: './src/app/core/api/generated',
      client: 'angular',
      override: {
        angular: {
          provideIn: 'root'
        }
      }
    }
  }
});
