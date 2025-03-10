import styled from '@emotion/styled';

import {Button} from 'sentry/components/button';
import IdBadge from 'sentry/components/idBadge';
import {PanelItem} from 'sentry/components/panels';
import RoleSelectControl from 'sentry/components/roleSelectControl';
import {IconSubtract} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import {Member, Organization, Team, TeamMember, User} from 'sentry/types';
import {getEffectiveOrgRole} from 'sentry/utils/orgRole';
import {
  hasOrgRoleOverwrite,
  RoleOverwriteIcon,
} from 'sentry/views/settings/organizationTeams/roleOverwriteWarning';
import {getButtonHelpText} from 'sentry/views/settings/organizationTeams/utils';

function TeamMembersRow(props: {
  hasWriteAccess: boolean;
  isOrgOwner: boolean;
  member: TeamMember;
  organization: Organization;
  removeMember: (member: Member) => void;
  team: Team;
  updateMemberRole: (member: Member, newRole: string) => void;
  user: User;
}) {
  const {
    organization,
    team,
    member,
    user,
    hasWriteAccess,
    isOrgOwner,
    removeMember,
    updateMemberRole,
  } = props;

  return (
    <TeamRolesPanelItem key={member.id}>
      <div>
        <IdBadge avatarSize={36} member={member} useLink orgId={organization.slug} />
      </div>
      <div>
        <TeamRoleSelect
          hasWriteAccess={hasWriteAccess}
          updateMemberRole={updateMemberRole}
          organization={organization}
          team={team}
          member={member}
        />
      </div>
      <div>
        <RemoveButton
          hasWriteAccess={hasWriteAccess}
          hasOrgRoleFromTeam={team.orgRole !== null}
          isOrgOwner={isOrgOwner}
          onClick={() => removeMember(member)}
          member={member}
          user={user}
        />
      </div>
    </TeamRolesPanelItem>
  );
}

function TeamRoleSelect(props: {
  hasWriteAccess: boolean;
  member: TeamMember;
  organization: Organization;
  team: Team;
  updateMemberRole: (member: TeamMember, newRole: string) => void;
}) {
  const {hasWriteAccess, organization, team, member, updateMemberRole} = props;
  const {orgRoleList, teamRoleList, features} = organization;
  if (!features.includes('team-roles')) {
    return null;
  }

  // Determine the team-role, including if the current team has an org role
  // and if adding the user to the current team changes their minimum team-role
  const possibleOrgRoles = [member.orgRole];
  if (member.orgRolesFromTeams && member.orgRolesFromTeams.length > 0) {
    possibleOrgRoles.push(member.orgRolesFromTeams[0].role.id);
  }
  if (team.orgRole) {
    possibleOrgRoles.push(team.orgRole);
  }
  const effectiveOrgRole = getEffectiveOrgRole(possibleOrgRoles, orgRoleList);

  const teamRoleId = member.teamRole || effectiveOrgRole?.minimumTeamRole;
  const teamRole = teamRoleList.find(r => r.id === teamRoleId) || teamRoleList[0];

  if (
    !hasWriteAccess ||
    hasOrgRoleOverwrite({orgRole: effectiveOrgRole?.id, orgRoleList, teamRoleList})
  ) {
    return (
      <RoleName>
        {teamRole.name}
        <IconWrapper>
          <RoleOverwriteIcon
            orgRole={effectiveOrgRole?.id}
            orgRoleList={orgRoleList}
            teamRoleList={teamRoleList}
          />
        </IconWrapper>
      </RoleName>
    );
  }

  return (
    <RoleSelectWrapper>
      <RoleSelectControl
        roles={teamRoleList}
        value={teamRole.id}
        onChange={option => updateMemberRole(member, option.value)}
        disableUnallowed
      />
    </RoleSelectWrapper>
  );
}

function RemoveButton(props: {
  hasOrgRoleFromTeam: boolean;
  hasWriteAccess: boolean;
  isOrgOwner: boolean;
  member: TeamMember;
  onClick: () => void;
  user: User;
}) {
  const {member, user, hasWriteAccess, isOrgOwner, hasOrgRoleFromTeam, onClick} = props;

  const isSelf = member.email === user.email;
  const canRemoveMember = hasWriteAccess || isSelf;
  if (!canRemoveMember) {
    return null;
  }
  const isIdpProvisioned = member.flags['idp:provisioned'];
  const isPermissionGroup = hasOrgRoleFromTeam && !isOrgOwner;

  const buttonHelpText = getButtonHelpText(isIdpProvisioned, isPermissionGroup);

  if (isIdpProvisioned || isPermissionGroup) {
    return (
      <Button
        size="xs"
        disabled
        icon={<IconSubtract size="xs" isCircled />}
        onClick={onClick}
        aria-label={t('Remove')}
        title={buttonHelpText}
      >
        {t('Remove')}
      </Button>
    );
  }
  return (
    <Button
      size="xs"
      disabled={!canRemoveMember}
      icon={<IconSubtract size="xs" isCircled />}
      onClick={onClick}
      aria-label={t('Remove')}
    >
      {t('Remove')}
    </Button>
  );
}

const RoleName = styled('div')`
  display: flex;
  align-items: center;
`;
const IconWrapper = styled('div')`
  height: ${space(2)};
  margin-left: ${space(1)};
`;

const RoleSelectWrapper = styled('div')`
  display: flex;
  flex-direction: row;
  align-items: center;

  > div:first-child {
    flex-grow: 1;
  }
`;

const TeamRolesPanelItem = styled(PanelItem)`
  display: grid;
  grid-template-columns: minmax(120px, 4fr) minmax(120px, 2fr) minmax(100px, 1fr);
  gap: ${space(2)};
  align-items: center;

  > div:last-child {
    margin-left: auto;
  }
`;

export default TeamMembersRow;
