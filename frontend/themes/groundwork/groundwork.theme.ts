// The groundwork theme. `astryx experimental theme editor` wrote this file once and never changes it again.
// The checked settings live in groundwork.settings.json and the generated groundwork.settings.ts;
// change them with `astryx experimental theme editor set groundwork ...`. Add your own changes below: they win over the settings.
import {defineTheme} from '@astryxdesign/core/theme';
import {groundworkSettings} from './groundwork.settings';

export const groundworkTheme = defineTheme({
  extends: groundworkSettings,
  name: 'groundwork',
});
