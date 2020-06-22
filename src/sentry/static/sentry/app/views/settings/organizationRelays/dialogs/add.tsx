import {t} from 'app/locale';
import {addErrorMessage} from 'app/actionCreators/indicator';

import DialogManager from './dialogManager';

type Props = DialogManager['props'];

type State = DialogManager['state'];

class Add extends DialogManager<Props, State> {
  getTitle() {
    return t('New Relay Key');
  }

  async handleSave() {
    const {onSubmitSuccess, closeModal, savedRelays, orgSlug, api} = this.props;

    const trustedRelays = [...savedRelays, this.state.values];

    try {
      const response = await api.requestPromise(`/organizations/${orgSlug}/`, {
        method: 'PUT',
        data: {trustedRelays},
      });
      onSubmitSuccess(response);
      closeModal();
    } catch (error) {
      // TODO(Priscila): threat error response
      addErrorMessage('An unknown error occurred while saving relay public key');
    }
  }
}

export default Add;
