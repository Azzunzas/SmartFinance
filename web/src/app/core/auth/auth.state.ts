import { Injectable, computed, signal } from '@angular/core';

export type AuthenticationStatus = 'unknown' | 'authenticated' | 'anonymous';

@Injectable({ providedIn: 'root' })
export class AuthState {
  readonly status = signal<AuthenticationStatus>('unknown');
  readonly username = signal<string | null>(null);
  readonly isAuthenticated = computed(() => this.status() === 'authenticated');

  authenticate(username: string): void {
    this.username.set(username);
    this.status.set('authenticated');
  }

  clear(): void {
    this.username.set(null);
    this.status.set('anonymous');
  }
}
