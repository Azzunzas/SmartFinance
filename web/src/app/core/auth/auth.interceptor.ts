import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthState } from './auth.state';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const router = inject(Router);
  const state = inject(AuthState);
  const authenticatedRequest = request.clone({ withCredentials: true });

  return next(authenticatedRequest).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401) {
        state.clear();
        void router.navigateByUrl('/login');
      }
      return throwError(() => error);
    }),
  );
};
