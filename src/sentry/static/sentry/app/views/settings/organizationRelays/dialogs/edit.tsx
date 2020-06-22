import {t} from 'app/locale';
import {addErrorMessage} from 'app/actionCreators/indicator';

import {Relay} from '../types';
import DialogManager from './dialogManager';

type Props = {
  relay: Relay;
} & DialogManager['props'];

type State = DialogManager['state'];

class Edit extends DialogManager<Props, State> {
  getDefaultState() {
    return {
      ...super.getDefaultState(),
      values: {
        name: this.props.relay.name,
        publicKey: this.props.relay.publicKey,
        description: this.props.relay.description || '',
      },
      disables: {publicKey: true},
    };
  }

  getTitle() {
    return t('Edit Relay Key');
  }

  async handleSave() {
    const {onSubmitSuccess, closeModal, savedRelays, orgSlug, api} = this.props;

    const updatedRelay = this.state.values;

    const trustedRelays = savedRelays.map(relay => {
      if (relay.publicKey === updatedRelay.publicKey) {
        return updatedRelay;
      }
      return relay;
    });

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

export default Edit;
