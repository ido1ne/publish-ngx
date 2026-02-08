import { Component, Input, OnInit, inject } from '@angular/core'
import { SETTINGS_KEYS } from 'src/app/data/ui-settings'
import { SettingsService } from 'src/app/services/settings.service'
import { environment } from 'src/environments/environment'
import { ActivatedRoute } from '@angular/router';

@Component({
  selector: 'pngx-logo',
  templateUrl: './logo.component.html',
  styleUrls: ['./logo.component.scss'],
})

export class LogoComponent implements OnInit {
  logoUrl: string;

  constructor(private route: ActivatedRoute) { }

  ngOnInit(): void {
    this.route.queryParams.subscribe(params => {
      const correspondentId = params['correspondent__id__in'];
      this.logoUrl = this.customLogo(correspondentId);
    });
  }

  customLogo(correspondentId: string): string {
    // Map correspondent ID to logo URL
    switch (correspondentId) {
      case '1':
        return 'logo1.png';
      case '2':
        return 'logo2.png';
      case '3':
        return 'logo3.png';
      default:
        return 'assets/logos/default.png'; // Default logo
    }
  }
}

/*
export class LogoComponent {
  private settingsService = inject(SettingsService)

  @Input()
  extra_classes: string

  @Input()
  height = '6em'


  get customLogo(): string {
    return this.settingsService.get(SETTINGS_KEYS.APP_LOGO)?.length
      ? environment.apiBaseUrl.replace(
          /\/api\/$/,
          this.settingsService.get(SETTINGS_KEYS.APP_LOGO)
        )
      : null
  }



getClasses() {
  return ['logo'].concat(this.extra_classes).join(' ')
}
}
*/