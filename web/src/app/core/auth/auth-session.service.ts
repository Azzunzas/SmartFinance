import { Injectable, inject } from '@angular/core';
import { Observable, catchError, finalize, map, of, tap } from 'rxjs';

import { AuthService } from '../api/generated/auth/auth.service';
import { LoginRequest, RegisterRequest } from '../api/generated/smartFinanceAPI.schemas';
import { AuthState } from './auth.state';

@Injectable({ providedIn: 'root' })
export class AuthSessionService {
  private readonly api = inject(AuthService);
  private readonly state = inject(AuthState);

  checkSession(): Observable<boolean> {
    if (this.state.status() !== 'unknown') {
      return of(this.state.isAuthenticated());
    }

    return this.api.meApiAuthMeGet().pipe(
      tap((me) => this.state.authenticate(me.username)),
      map(() => true),
      catchError(() => {
        this.state.clear();
        return of(false);
      }),
    );
  }

  login(credentials: LoginRequest): Observable<void> {
    return this.api.loginApiAuthLoginPost(credentials).pipe(
      tap((me) => this.state.authenticate(me.username)),
      map(() => undefined),
    );
  }

  register(credentials: RegisterRequest): Observable<void> {
    return this.api.registerApiAuthRegisterPost(credentials).pipe(
      tap((me) => this.state.authenticate(me.username)),
      map(() => undefined),
    );
  }

  logout(): Observable<void> {
    return this.api.logoutApiAuthLogoutPost().pipe(finalize(() => this.state.clear()));
  }
}
