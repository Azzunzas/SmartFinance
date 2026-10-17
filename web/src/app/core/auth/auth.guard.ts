import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map } from 'rxjs';

import { AuthSessionService } from './auth-session.service';

export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  return inject(AuthSessionService)
    .checkSession()
    .pipe(map((authenticated) => authenticated || router.createUrlTree(['/login'])));
};

export const guestGuard: CanActivateFn = () => {
  const router = inject(Router);
  return inject(AuthSessionService)
    .checkSession()
    .pipe(map((authenticated) => (authenticated ? router.createUrlTree(['/overview']) : true)));
};
