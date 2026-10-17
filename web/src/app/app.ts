import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthSessionService } from './core/auth/auth-session.service';
import { AuthState } from './core/auth/auth.state';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly router = inject(Router);
  private readonly session = inject(AuthSessionService);
  protected readonly authState = inject(AuthState);
  protected readonly sidebarCollapsed = signal(false);

  protected logout(): void {
    this.session.logout().subscribe(() => this.router.navigateByUrl('/login'));
  }
}
